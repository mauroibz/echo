"""The model stuck repeating itself: never kept from a retry, cut down and marked when it stays."""

import numpy as np

from echo_app.worker import asr


def _engine(answers):
    """An engine whose model answers in turn from `answers` (text, log-probability) per call."""
    eng = asr.Engine.__new__(asr.Engine)
    calls = []

    def batch(clips, adapter, context, bare=False, language="es"):
        calls.append(len(clips))
        return [answers[min(len(calls) - 1, len(answers) - 1)]] * len(clips)

    eng._transcribe_batch = batch
    return eng, calls


def test_loops_are_recognized():
    assert asr.looping("Esto es para. " + "para. " * 39 + "para.")
    assert asr.looping("Y, y, y, y, y, y, y, y, y, y,")
    for real in ("Sí, sí, sí.", "No, no, no, no.", "Dale, dale, dale.", "Por favor, por ejemplo, por lo tanto."):
        assert not asr.looping(real)
    assert asr.unloop("Esto es para. " + "para. " * 39 + "para.") == "Esto es para. para. para."


def test_a_retry_into_a_loop_is_not_kept():
    clip = np.zeros(16000 * 20, dtype=np.int16)
    # Unsure, then a retry that is more confident but loops: the first text stays.
    eng, _ = _engine([("Y en este caso lo vemos la semana que viene, con todos", -1.13),
                      ("Y, y, y, y, y, y, y, y, y, y, y, y, y, y,", -0.69)])
    (text, flags, lp), = eng.transcribe_flagged([clip])
    assert text.startswith("Y en este caso") and lp == -1.13 and "retried" not in flags


def test_a_loop_is_retried_and_if_it_stays_cut_down_and_marked():
    clip = np.zeros(16000 * 5, dtype=np.int16)
    loop = "Bueno, sigamos. Esto es para. " + "para. " * 39
    eng, calls = _engine([(loop, -0.22), ("Bueno, sigamos. Esto es para el lunes.", -0.2)])
    (text, flags, _lp), = eng.transcribe_flagged([clip])
    assert text == "Bueno, sigamos. Esto es para el lunes." and flags == ["retried"]
    eng, calls = _engine([(loop, -0.22)])
    (text, flags, _lp), = eng.transcribe_flagged([clip])
    assert text == "Bueno, sigamos. Esto es para. para." and flags == ["loop"] and len(calls) == 3
