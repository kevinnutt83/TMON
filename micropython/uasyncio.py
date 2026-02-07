"""
CPython shim for MicroPython's `uasyncio`.

Purpose: allow TMON firmware modules that do `import uasyncio as asyncio`
to run under Python 3 on Raspberry Pi Zero.

This intentionally implements only the small surface used in this repo.
"""

import asyncio as _a

# Commonly used API surface
sleep = _a.sleep
gather = _a.gather
create_task = _a.create_task
CancelledError = _a.CancelledError
TimeoutError = _a.TimeoutError

Lock = _a.Lock
Event = _a.Event

def get_event_loop():
	# Python 3.10+: get_event_loop is deprecated in some contexts; keep compatibility.
	try:
		return _a.get_event_loop()
	except RuntimeError:
		loop = _a.new_event_loop()
		_a.set_event_loop(loop)
		return loop

def run(coro):
	return _a.run(coro)

# Convenience helpers occasionally used in MicroPython code
async def sleep_ms(ms):
	await _a.sleep(float(ms) / 1000.0)
