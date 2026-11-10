"""
test_multi_file_ui.py — Integration tests for multi-file loading, UI controls, and workflows.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from unittest.mock import patch, MagicMock
import numpy as np
from PySide6.QtWidgets import QApplication
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.models.log_session import LogSession
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.gui.main_window import MainWindow
from uavlogviewer.widgets.param_diff_dialog import ParamDiffDialog

app = QApplication.instance() or QApplication([])

class TestMultiFileUI(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()

        # Create two mock parsed logs
        self.log1 = ParsedLog(filename="flight1.bin", log_type="dataflash")
        t1 = np.linspace(100.0, 110.0, 50)
        self.log1.timestamps["ATT"] = t1
        self.log1.time_series["ATT.Roll"] = np.sin(t1)
        self.log1.field_tree = {"ATT": ["Roll"]}
        self.log1.params = {"BATT_CAPACITY": 5000, "MOT_SPIN_ARM": 0.15}

        self.log2 = ParsedLog(filename="flight2.bin", log_type="dataflash")
        t2 = np.linspace(200.0, 210.0, 50)
        self.log2.timestamps["ATT"] = t2
        self.log2.time_series["ATT.Roll"] = np.cos(t2)
        self.log2.field_tree = {"ATT": ["Roll"]}
        self.log2.params = {"BATT_CAPACITY": 5200, "MOT_SPIN_ARM": 0.15}

    def tearDown(self):
        self.window.close_all_logs()
        self.window.close()

    def test_session_multi_loading_and_labels(self):
        l1 = self.window.session.add_log(self.log1, "/fake/flight1.bin")
        l2 = self.window.session.add_log(self.log2, "/fake/flight2.bin")

        self.assertEqual(len(self.window.session.logs), 2)
        self.assertTrue(self.window.session.is_multi)
        self.assertEqual(l1.label, "F1")
        self.assertEqual(l2.label, "F2")

        # Source combo in sidebar should have 2 items
        self.assertEqual(self.window.sidebar.cmb_source_log.count(), 2)
        self.assertFalse(self.window.sidebar.source_box.isHidden())

    def test_add_expression_for_all_logs(self):
        l1 = self.window.session.add_log(self.log1, "/fake/flight1.bin")
        l2 = self.window.session.add_log(self.log2, "/fake/flight2.bin")

        self.window.sidebar.add_field_for_all_logs(0, "ATT.Roll")
        chart = self.window.chart_store.charts[0]
        self.assertEqual(len(chart.expressions), 2)
        self.assertEqual(chart.expressions[0].log_id, l1.log_id)
        self.assertEqual(chart.expressions[1].log_id, l2.log_id)

    def test_param_diff_dialog(self):
        self.window.session.add_log(self.log1, "/fake/flight1.bin")
        self.window.session.add_log(self.log2, "/fake/flight2.bin")

        dialog = ParamDiffDialog(self.window.session)
        # BATT_CAPACITY differs (5000 vs 5200), MOT_SPIN_ARM is identical
        # With only_diff=True default, table should have 1 row
        self.assertEqual(dialog.table.rowCount(), 1)
        self.assertEqual(dialog.table.item(0, 0).text(), "BATT_CAPACITY")

        # Toggle only_diff to False -> should have 2 rows
        dialog.chk_only_diff.setChecked(False)
        self.assertEqual(dialog.table.rowCount(), 2)

    def test_close_log_and_close_all(self):
        l1 = self.window.session.add_log(self.log1, "/fake/flight1.bin")
        l2 = self.window.session.add_log(self.log2, "/fake/flight2.bin")
        self.window.sidebar.add_field_for_all_logs(0, "ATT.Roll")

        # Close log 1
        self.window.close_log(l1.log_id)
        self.assertEqual(len(self.window.session.logs), 1)
        self.assertEqual(self.window.session.active_log_id, l2.log_id)
        # Chart expressions for log 1 removed
        self.assertEqual(len(self.window.chart_store.charts[0].expressions), 1)
        self.assertEqual(self.window.chart_store.charts[0].expressions[0].log_id, l2.log_id)

        # Close all
        self.window.close_all_logs()
        self.assertEqual(len(self.window.session.logs), 0)
        self.assertFalse(self.window.chart_store.has_any_expressions())

    def test_sidebar_files_opened_worker_concurrency(self):
        import tempfile
        import time

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("timestamp,ATT.Roll\n0.0,1.0\n0.1,2.0\n")
            tmp_path = f.name

        try:
            # Emit files_opened as sidebar does
            self.window.sidebar.files_opened.emit([tmp_path])

            # Wait for worker thread to finish
            start = time.time()
            while (self.window.worker is not None or self.window._parse_queue) and time.time() - start < 5:
                app.processEvents()
                time.sleep(0.02)

            self.assertEqual(len(self.window.session.logs), 1)
            self.assertEqual(self.window.session.logs[0].filepath, tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @patch("uavlogviewer.gui.sidebar.QMenu.exec_")
    def test_tree_context_menu_options(self, mock_exec):
        l1 = self.window.session.add_log(self.log1, "/fake/flight1.bin")
        l2 = self.window.session.add_log(self.log2, "/fake/flight2.bin")
        self.window.sidebar.populate_field_tree(self.log1)
        self.window.show()

        # Find and expand ATT item in tree
        tree = self.window.sidebar.tree
        att_item = None
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            if top.text(0).startswith("ATT"):
                top.setExpanded(True)
                for j in range(top.childCount()):
                    if top.child(j).text(0) == "Roll":
                        att_item = top.child(j)
                        break

        self.assertIsNotNone(att_item)
        rect = tree.visualItemRect(att_item)
        self.window.sidebar.show_tree_context_menu(rect.center())
        mock_exec.assert_called_once()


class TestLoadedLogsCards(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.log1 = ParsedLog(filename="flight1.bin", log_type="dataflash")
        t1 = np.linspace(100.0, 110.0, 50)
        self.log1.timestamps["ATT"] = t1
        self.log1.time_series["ATT.Roll"] = np.sin(t1)
        self.log1.field_tree = {"ATT": ["Roll"]}
        self.log2 = ParsedLog(filename="flight2.bin", log_type="dataflash")
        t2 = np.linspace(200.0, 215.0, 50)
        self.log2.timestamps["ATT"] = t2
        self.log2.time_series["ATT.Roll"] = np.cos(t2)
        self.log2.field_tree = {"ATT": ["Roll"]}
        self.l1 = self.window.session.add_log(self.log1, "/fake/flight1.bin")
        self.l2 = self.window.session.add_log(self.log2, "/fake/flight2.bin")
        self.window.sidebar.nav_tabs.setCurrentIndex(0)

    def tearDown(self):
        self.window.close_all_logs()
        self.window.close()

    def _wait(self, ms):
        import time
        end = time.time() + ms / 1000.0
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)

    def test_duration_computed(self):
        self.assertAlmostEqual(self.l2.duration, 15.0)

    def test_offset_change_keeps_home_tab_and_spinbox(self):
        sb = self.window.sidebar
        card = sb._log_cards[self.l1.log_id]
        spin = card.spin
        spin.setValue(1.5)
        self._wait(500)
        self.assertEqual(sb.nav_tabs.currentIndex(), 0)
        self.assertIs(sb._log_cards[self.l1.log_id], card)
        self.assertIs(sb._log_cards[self.l1.log_id].spin, spin)
        self.assertAlmostEqual(self.l1.user_offset, 1.5)

    def test_offset_is_debounced(self):
        card = self.window.sidebar._log_cards[self.l1.log_id]
        fired = []
        self.window.session.offsets_changed.connect(lambda: fired.append(1))
        for v in (0.1, 0.2, 0.3, 0.4):
            card.spin.setValue(v)
        self.assertEqual(len(fired), 0)
        self._wait(500)
        self.assertEqual(len(fired), 1)
        self.assertAlmostEqual(self.l1.user_offset, 0.4)

    def test_reset_all_offsets(self):
        self.window.session.set_user_offset(self.l1.log_id, 2.0)
        self.window.session.set_user_offset(self.l2.log_id, -3.0)
        fired = []
        self.window.session.offsets_changed.connect(lambda: fired.append(1))
        self.window.sidebar.btn_reset_offsets.click()
        self.assertEqual(len(fired), 1)
        self.assertEqual(self.l1.user_offset, 0.0)
        self.assertEqual(self.l2.user_offset, 0.0)
        for card in self.window.sidebar._log_cards.values():
            self.assertEqual(card.spin.value(), 0.0)

    def test_click_card_sets_active_without_tab_switch(self):
        sb = self.window.sidebar
        self.assertEqual(self.window.session.active_log_id, self.l1.log_id)
        sb._log_cards[self.l2.log_id].activate_requested.emit(self.l2.log_id)
        self.assertEqual(self.window.session.active_log_id, self.l2.log_id)
        self.assertEqual(sb.nav_tabs.currentIndex(), 0)
        self.assertIs(sb.parsed_log, self.log2)

    def test_new_load_still_switches_to_plot_tab(self):
        sb = self.window.sidebar
        sb.nav_tabs.setCurrentIndex(0)
        self.window.on_log_parsed(self.log1)
        self.assertEqual(sb.nav_tabs.currentIndex(), 1)

    def test_offset_change_triggers_plot_refresh(self):
        from unittest.mock import patch as _patch
        pc = self.window.plot_container
        with _patch.object(pc, "update_plots") as m:
            pc._session_refresh_timer.timeout.disconnect()
            pc._session_refresh_timer.timeout.connect(pc.update_plots)
            self.window.session.set_user_offset(self.l1.log_id, 2.0)
            self._wait(200)
            self.assertGreaterEqual(m.call_count, 1)
