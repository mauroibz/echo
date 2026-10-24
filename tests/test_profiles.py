"""Compute profiles, the CPU engine settings and the measured-speed estimate (no torch needed)."""

import importlib.metadata

import pytest

from echo_app import doctor, features, transcription
from echo_app.worker import asr


@pytest.fixture
def profile(monkeypatch):
    def set_version(version):
        features.compute_profile.cache_clear()
        monkeypatch.setattr(features, "transcription_installed", lambda: True)
        monkeypatch.setattr(importlib.metadata, "version", lambda name: version)

    yield set_version
    features.compute_profile.cache_clear()


def test_profile_from_torch_build(profile):
    for version, expected in (("2.14.1", features.CUDA), ("2.14.1+cpu", features.CPU),
                              ("2.14.1+rocm7.2", features.ROCM), ("2.14.1+cu130", features.CUDA)):
        profile(version)
        assert features.compute_profile() == expected, version


def test_base_profile_without_transcription(monkeypatch):
    features.compute_profile.cache_clear()
    monkeypatch.setattr(features, "transcription_installed", lambda: False)
    assert features.compute_profile() == features.BASE
    features.compute_profile.cache_clear()


def test_doctor_profile_matches_hardware():
    assert doctor.check_profile(features.CUDA, features.CUDA).status == doctor.OK
    c = doctor.check_profile(features.CUDA, features.CPU)
    assert c.status == doctor.WARN and "--with-transcription=cpu" in c.fix and "NVIDIA" in c.detail
    c = doctor.check_profile(features.CPU, features.CUDA)
    assert c.status == doctor.WARN and c.fix == "./install.sh --with-transcription=cuda"
    assert doctor.check_profile(features.ROCM, features.CPU).fix.startswith("./install.sh --with-transcription=cpu")


def test_speed_estimate_before_and_after_jobs(monkeypatch):
    monkeypatch.setattr(features, "compute_profile", lambda: features.CPU)
    minutes, measured = transcription.minutes_per_hour()
    assert minutes == transcription.EXPECTED_MIN_PER_HOUR[features.CPU] and not measured
    assert "typical computer" in transcription.speed_text()
    # Short jobs alone do not count as a measurement; together they do.
    transcription.record_speed("cpu", 30, 10)
    assert not transcription.minutes_per_hour()[1]
    transcription.record_speed("cpu", 3600 - 30, 600 - 10)
    minutes, measured = transcription.minutes_per_hour()
    assert measured and minutes == pytest.approx(10.0)
    assert transcription.speed_text() == "Transcription takes about 10 minutes per hour of audio on this computer."


def test_speed_keeps_recent_jobs_only():
    for i in range(transcription.SPEED_JOBS + 5):
        transcription.record_speed("cuda", 600, 60 if i < 5 else 6)
    minutes, measured = transcription.minutes_per_hour("cuda")
    assert measured and minutes == pytest.approx(0.6)


def test_speed_key_follows_the_device(monkeypatch):
    monkeypatch.setattr(features, "compute_profile", lambda: features.CUDA)
    assert transcription.speed_key("cuda") == features.CUDA
    assert transcription.speed_key("cpu") == features.CPU  # a GPU profile that fell back to the processor


def test_cpu_batch_size_by_memory():
    assert asr.cpu_batch_size(16_000_000_000) == 4
    assert asr.cpu_batch_size(4_000_000_000) == 2
    assert asr.cpu_batch_size(1_000_000_000) == 1
    assert asr.cpu_batch_size(None) == 2


def test_physical_cores_and_memory_are_positive():
    assert asr.physical_cores() >= 1
    mem = asr.available_memory()
    assert mem is None or mem > 0


def test_cpu_out_of_memory_is_recognized():
    assert asr.is_oom(MemoryError())
    assert asr.is_oom(RuntimeError("DefaultCPUAllocator: can't allocate memory: you tried to allocate 1 bytes; "
                                   "failed to allocate"))
    assert not asr.is_oom(ValueError("bad"))


def test_gpu_usable_needs_bf16_and_free_memory():
    from types import SimpleNamespace

    from echo_app.worker import asr

    def fake(available=True, bf16=True, free_gb=8.0):
        cuda = SimpleNamespace(is_available=lambda: available,
                               is_bf16_supported=lambda including_emulation=True: bf16,
                               mem_get_info=lambda: (int(free_gb * 2**30), 10 * 2**30))
        return SimpleNamespace(cuda=cuda)

    assert asr.gpu_usable(fake()) == (True, "")
    assert asr.gpu_usable(fake(free_gb=5.0))[0]  # a 6 GB card with the desktop on it
    ok, why = asr.gpu_usable(fake(free_gb=3.5))
    assert not ok and "3.5 GB" in why
    ok, why = asr.gpu_usable(fake(bf16=False))
    assert not ok and "RTX 30" in why
    assert not asr.gpu_usable(fake(available=False))[0]
