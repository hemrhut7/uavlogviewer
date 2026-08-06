"""
test_sidebar_tree_filter.py — Unit tests for Log Fields Tree search filter preservation in SidebarWidget.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from PySide6.QtWidgets import QApplication
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.gui.sidebar import SidebarWidget

app = QApplication.instance() or QApplication([])

class TestSidebarTreeFilter(unittest.TestCase):
    def setUp(self):
        self.chart_store = ChartStore()
        self.sidebar = SidebarWidget(self.chart_store)
        self.log = ParsedLog(filename="test_filter.bin", log_type="dataflash")
        self.log.field_tree = {
            "ATT": ["Pitch", "Roll", "Yaw"],
            "BARO": ["Alt", "CRt", "Press"],
            "GPS": ["Alt", "Lat", "Lng", "Spd"],
        }
        self.sidebar.populate_field_tree(self.log)

    def test_search_filter_maintained_after_repopulate(self):
        # 1. Type "ATT" into search input
        self.sidebar.search_input.setText("ATT")
        
        # Verify initial filtering state
        tree = self.sidebar.tree
        att_item = None
        baro_item = None
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item.text(0).startswith("ATT"):
                att_item = item
            elif item.text(0).startswith("BARO"):
                baro_item = item

        self.assertIsNotNone(att_item)
        self.assertIsNotNone(baro_item)
        self.assertFalse(att_item.isHidden())
        self.assertTrue(baro_item.isHidden())

        # 2. Simulate chart content update / repopulating field tree
        self.log.field_tree["CALC"] = ["ATT.Roll + 10"]
        self.sidebar.populate_field_tree(self.log)

        # 3. Assert search input text is still "ATT" and filter is STILL APPLIED
        self.assertEqual(self.sidebar.search_input.text(), "ATT")

        new_att_item = None
        new_baro_item = None
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item.text(0).startswith("ATT"):
                new_att_item = item
            elif item.text(0).startswith("BARO"):
                new_baro_item = item

        self.assertIsNotNone(new_att_item)
        self.assertIsNotNone(new_baro_item)
        # BARO must remain hidden, ATT must remain visible!
        self.assertFalse(new_att_item.isHidden(), "ATT item should be visible")
        self.assertTrue(new_baro_item.isHidden(), "BARO item should remain hidden after repopulate")

    def test_expanded_state_maintained_when_no_search_query(self):
        self.sidebar.search_input.setText("")
        tree = self.sidebar.tree
        
        # Expand ATT category manually
        att_item = None
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item.text(0).startswith("ATT"):
                att_item = item
                item.setExpanded(True)
                break

        self.assertTrue(att_item.isExpanded())

        # Repopulate tree
        self.sidebar.populate_field_tree(self.log)

        # Check that ATT category is still expanded
        new_att_item = None
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item.text(0).startswith("ATT"):
                new_att_item = item
                break

        self.assertTrue(new_att_item.isExpanded(), "ATT item should remain expanded after repopulate when search query is empty")


if __name__ == "__main__":
    unittest.main()
