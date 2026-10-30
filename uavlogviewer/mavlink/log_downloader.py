"""
log_downloader.py — High-speed chunked MAVLink DataFlash onboard log list & download workers using mmap.
"""
import mmap
import time
from typing import List, Optional
from PySide6.QtCore import QThread, Signal


class LogListWorker(QThread):
    entry_received = Signal(int, int, int, int)  # log_id, num_logs, time_utc, size
    finished = Signal(list)  # list of log info dicts
    error = Signal(str)

    def __init__(self, master, target_system: int, target_component: int, parent=None):
        super().__init__(parent)
        self.master = master
        self.target_system = target_system
        self.target_component = target_component
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            if not self.master:
                raise Exception("MAVLink connection not open")

            # Clean buffer
            while self.master.recv_match(blocking=False):
                pass

            # Send log request list
            self.master.mav.log_request_list_send(
                self.target_system,
                self.target_component,
                0, 0xFFFF
            )

            logs = []
            expected_count = None
            t_start = time.time()
            timeout = 6.0

            while not self.is_cancelled:
                msg = self.master.recv_match(type='LOG_ENTRY', blocking=True, timeout=0.5)
                if msg:
                    t_start = time.time()
                    log_id = msg.id
                    num_logs = msg.num_logs
                    time_utc = msg.time_utc
                    size = msg.size

                    if num_logs == 0:
                        break

                    entry = {
                        'id': log_id,
                        'num_logs': num_logs,
                        'time_utc': time_utc,
                        'size': size
                    }
                    if not any(x['id'] == log_id for x in logs):
                        logs.append(entry)
                        self.entry_received.emit(log_id, num_logs, time_utc, size)

                    if expected_count is None:
                        expected_count = num_logs

                    if len(logs) >= expected_count:
                        break
                else:
                    if time.time() - t_start > timeout:
                        if expected_count is not None and len(logs) > 0:
                            break
                        else:
                            raise Exception("Timeout waiting for onboard log list")

            self.finished.emit(logs)
        except Exception as e:
            self.error.emit(str(e))


class LogDownloadWorker(QThread):
    # completed_bytes, percent, speed_bytes_sec, packets_recv, duplicates, timeouts, retries
    progress = Signal(int, float, float, int, int, int, int)
    finished = Signal(str)  # save_path
    status = Signal(str)
    error = Signal(str)

    def __init__(self, master, target_system: int, target_component: int, log_id: int, log_size: int, save_path: str, parent=None):
        super().__init__(parent)
        self.master = master
        self.target_system = target_system
        self.target_component = target_component
        self.log_id = log_id
        self.log_size = log_size
        self.save_path = save_path
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        m = None
        f = None
        try:
            if not self.master:
                raise Exception("MAVLink connection not open")

            f = open(self.save_path, "w+b")
            if self.log_size > 0:
                f.truncate(self.log_size)
                f.flush()
                m = mmap.mmap(f.fileno(), self.log_size, access=mmap.ACCESS_WRITE)
            else:
                raise Exception("Log size is zero.")

            chunk_size = 2048 * 90  # 180 KB
            completed_bytes = 0
            chunk_start = 0

            packets_recv = 0
            duplicates = 0
            timeouts = 0
            retries = 0

            t_start = time.time()
            t_last_progress = time.time()
            bytes_last_progress = 0

            # Drain buffer
            while self.master.recv_match(blocking=False):
                pass

            while chunk_start < self.log_size and not self.is_cancelled:
                this_chunk_size = min(chunk_size, self.log_size - chunk_start)
                num_blocks = (this_chunk_size + 89) // 90
                received_blocks = [False] * num_blocks

                self.master.mav.log_request_data_send(
                    self.target_system, self.target_component, self.log_id, chunk_start, this_chunk_size
                )

                t_last_packet = time.time()
                chunk_timeout = 0.6

                while not all(received_blocks) and not self.is_cancelled:
                    msg = self.master.recv_match(type='LOG_DATA', blocking=True, timeout=0.005)
                    if msg:
                        if msg.id == self.log_id:
                            packets_recv += 1
                            ofs = msg.ofs
                            if chunk_start <= ofs < chunk_start + this_chunk_size:
                                block_idx = (ofs - chunk_start) // 90
                                if not received_blocks[block_idx]:
                                    data_chunk = bytes(msg.data[:msg.count])
                                    m[ofs:ofs+len(data_chunk)] = data_chunk
                                    received_blocks[block_idx] = True
                                    completed_bytes += len(data_chunk)
                                    t_last_packet = time.time()
                                else:
                                    duplicates += 1
                    else:
                        if time.time() - t_last_packet > chunk_timeout:
                            timeouts += 1
                            if retries > 10:
                                raise Exception(f"Too many timeouts downloading chunk at offset {chunk_start}")
                            retries += 1
                            # Re-request missing blocks in this chunk
                            self.master.mav.log_request_data_send(
                                self.target_system, self.target_component, self.log_id, chunk_start, this_chunk_size
                            )
                            t_last_packet = time.time()

                    now = time.time()
                    if now - t_last_progress >= 0.2:
                        speed = (completed_bytes - bytes_last_progress) / max(0.001, now - t_last_progress)
                        percent = (completed_bytes / self.log_size) * 100.0
                        self.progress.emit(completed_bytes, percent, speed, packets_recv, duplicates, timeouts, retries)
                        t_last_progress = now
                        bytes_last_progress = completed_bytes

                chunk_start += this_chunk_size

            if m is not None:
                m.flush()
                m.close()
            if f is not None:
                f.close()

            if not self.is_cancelled:
                self.progress.emit(self.log_size, 100.0, 0.0, packets_recv, duplicates, timeouts, retries)
                self.finished.emit(self.save_path)

        except Exception as e:
            if m is not None:
                try: m.close()
                except Exception: pass
            if f is not None:
                try: f.close()
                except Exception: pass
            self.error.emit(str(e))
