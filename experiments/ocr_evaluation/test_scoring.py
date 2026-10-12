"""Guard against quietly deleting signs or matching a value in the wrong area."""
import unittest

from score import contains_token, field_input_box, overlap, region_text


class ScoringTests(unittest.TestCase):
    def test_spaces_and_equivalent_microseconds_are_normalized(self):
        self.assertTrue(contains_token("500 μs/div", "500us/div"))
        self.assertTrue(contains_token("Frequency 1.000 000 kHz", "1.000000kHz"))

    def test_prefix_case_and_signs_are_not_erased(self):
        self.assertFalse(contains_token("5.00mV", "5.00V"))
        self.assertFalse(contains_token("-2.500ms", "2.500ms"))
        self.assertFalse(contains_token("2.500ms", "-2.500ms"))
        self.assertFalse(contains_token("0.2Hz", "<2.0Hz"))
        self.assertFalse(contains_token("1.99931VAC", "+1.99931VAC"))

    def test_longer_number_cannot_count_as_exact(self):
        self.assertFalse(contains_token("12.500ms", "2.500ms"))
        self.assertFalse(contains_token("1.0000V", "1.000V"))
        self.assertFalse(contains_token("5.00Vpp", "5.00V"))

    def test_layout_separators_do_not_join_two_values(self):
        self.assertTrue(contains_token("500us/div 5.00Mpts 1.00GSa/s", "500us/div"))
        self.assertTrue(contains_token("500us/div 5.00Mpts 1.00GSa/s", "5.00Mpts"))
        self.assertTrue(contains_token("+1.99931 VAC", "+1.99931VAC"))

    def test_region_rejects_text_outside_target(self):
        lines = [{"box": [[0,0],[10,0],[10,10],[0,10]], "text": "200.00Hz", "confidence": 0.99},
                 {"box": [[100,100],[150,100],[150,120],[100,120]], "text": "wrong", "confidence": 0.9}]
        text, selected = region_text(lines, [100,100,150,120])
        self.assertEqual(text, "wrong")
        self.assertFalse(contains_token(text, "200.00Hz"))
        self.assertEqual(len(selected), 1)

    def test_same_row_split_digits_sign_and_unit_are_read_left_to_right(self):
        lines = [{"box":[[50,10],[90,10],[90,20],[50,20]],"text":"000kHz","confidence":.9},
                 {"box":[[10,13],[49,13],[49,23],[10,23]],"text":"1.000","confidence":.9}]
        text, selected = region_text(lines, [0,0,100,30])
        self.assertEqual(text, "1.000 000kHz")
        self.assertTrue(contains_token(text, "1.000000kHz"))

    def test_full_and_crop_coordinate_mapping(self):
        case = {"source_size":[400,300], "full_input_size":[200,150],
                "screen_box_pixels":[100,100,300,200], "crop_input_size":[200,100]}
        self.assertEqual(field_input_box(case, [0,0,1,1], "full_1800"), [50,50,150,100])
        self.assertEqual(field_input_box(case, [0,0,1,1], "crop_1800"), [0,0,200,100])
        self.assertEqual(overlap([0,0,1,1],[2,2,3,3]), 0)


if __name__ == "__main__":
    unittest.main()
