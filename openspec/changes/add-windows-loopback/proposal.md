# Proposal

## Why

"Computer audio" (recording a call) is Linux only after add-windows-support. On Windows the
equivalent is WASAPI loopback, which needs verification against the PortAudio build that
`sounddevice` ships before it can be promised.

## What Changes

- If the shipped PortAudio exposes loopback devices, list each output as a "Computer audio"
  source on Windows as on Linux. If not, evaluate `pyaudiowpatch` as a Windows-only dependency
  and decide with the numbers in hand; document the outcome either way.

## Impact

`audio/portaudio.py`, doctor, README. Blocked on a Windows tester.
