import subprocess, sys
import numpy as np
import pytest
from fingerprint.fingerprint import model_fingerprint, explanation_bytes, bytes_fingerprint
from fingerprint.pseudonym import case_pseudonym

P = {"w": np.arange(6, dtype=np.float32) / 7, "b": np.array([0.25], np.float32)}

def test_deterministic_100_times():
    assert len({model_fingerprint(P) for _ in range(100)}) == 1

def test_key_order_and_dtype_independent():
    other = {"b": np.array([0.25], np.float64), "w": (np.arange(6) / 7).astype(np.float64)}
    assert model_fingerprint(P) == model_fingerprint(other)

def test_other_process():
    code = ("import numpy as np;from fingerprint.fingerprint import model_fingerprint as f;"
            "print(f({'w':np.arange(6,dtype=np.float32)/7,'b':np.array([0.25],np.float32)}))")
    out = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
    assert out == model_fingerprint(P)

def test_one_bit_changes_fingerprint():
    q = {k: v.copy() for k, v in P.items()}
    q["w"].view(np.uint32)[0] ^= 1
    assert model_fingerprint(q) != model_fingerprint(P)

def test_negative_zero_normalised():
    a = {"w": np.array([0.0, 1.0], np.float32)}
    b = {"w": np.array([-0.0, 1.0], np.float32)}
    assert model_fingerprint(a) == model_fingerprint(b)

def test_nan_inf_rejected():
    for bad in (np.nan, np.inf):
        with pytest.raises(ValueError):
            model_fingerprint({"w": np.array([bad], np.float32)})

def test_shape_is_part_of_fingerprint():
    assert model_fingerprint({"w": np.zeros((2, 3), np.float32)}) != model_fingerprint({"w": np.zeros((3, 2), np.float32)})

def test_explanation_one_comma_detected():
    raw = explanation_bytes({"f0": 0.1234567, "f1": -0.5})
    assert bytes_fingerprint(raw) != bytes_fingerprint(raw.replace(b"0.123457", b"0.123458"))

def test_pseudonym():
    k = b"k"
    assert case_pseudonym(k, "patient-42") == case_pseudonym(k, "patient-42")
    assert case_pseudonym(k, "patient-42") != case_pseudonym(b"k2", "patient-42")
    assert "patient" not in case_pseudonym(k, "patient-42")
