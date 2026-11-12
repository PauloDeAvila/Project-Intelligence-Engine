"""Offline unit tests for Blender material specifications (no Blender required)."""
import unittest

from pie.blender.material_spec import fingerprint, normalize_spec


def valid():
    return {"version": 1, "materials": [
        {"name": "Brushed Steel", "base_color": "#AABBCC", "metallic": 1, "roughness": 0.4}
    ]}


class MaterialSpecTests(unittest.TestCase):
    def test_normalization_and_stable_fingerprint(self):
        a = valid()
        b = valid()
        b["materials"][0]["base_color"] = "#aabbcc"
        self.assertEqual(fingerprint(a), fingerprint(b))
        self.assertEqual(normalize_spec(a)["materials"][0]["metallic"], 1.0)

    def test_rejects_unsafe_extra_keys(self):
        a = valid()
        a["materials"][0]["python"] = "exec('bad')"
        with self.assertRaises(ValueError):
            normalize_spec(a)

    def test_rejects_invalid_values(self):
        for bad in (float("nan"), float("inf"), -0.1, 1.1, True, "0.5"):
            a = valid()
            a["materials"][0]["roughness"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize_spec(a)

    def test_rejects_duplicate_names(self):
        a = valid()
        a["materials"].append(dict(a["materials"][0]))
        with self.assertRaises(ValueError):
            normalize_spec(a)


if __name__ == "__main__":
    unittest.main()
