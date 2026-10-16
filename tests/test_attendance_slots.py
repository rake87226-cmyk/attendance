import unittest
from datetime import time

from app import choose_attendance_slot


class ChooseAttendanceSlotTests(unittest.TestCase):
    def test_fixed_check_ins_are_available_in_their_windows(self):
        self.assertEqual(
            choose_attendance_slot(time(9, 0), set()),
            (("morning", "9:00 - 9:15 AM"), None),
        )
        self.assertEqual(
            choose_attendance_slot(time(13, 15), set()),
            (("afternoon", "1:15 - 1:30 PM"), None),
        )

    def test_flexible_check_in_is_not_available_before_two(self):
        for scan_time in (time(9, 15), time(12, 0), time(13, 30), time(13, 59, 59)):
            with self.subTest(scan_time=scan_time):
                slot, error = choose_attendance_slot(scan_time, set())
                self.assertIsNone(slot)
                self.assertIn("from 2:00 PM to 5:00 PM", error)

    def test_flexible_check_in_is_available_from_two_until_five(self):
        for scan_time in (time(14, 0), time(16, 59, 59)):
            with self.subTest(scan_time=scan_time):
                self.assertEqual(
                    choose_attendance_slot(scan_time, set()),
                    (("flexible", "Flexible (2:00 - 5:00 PM)"), None),
                )

    def test_flexible_check_in_closes_at_five(self):
        slot, error = choose_attendance_slot(time(17, 0), set())
        self.assertIsNone(slot)
        self.assertIn("closed at 5:00 PM", error)


if __name__ == "__main__":
    unittest.main()
