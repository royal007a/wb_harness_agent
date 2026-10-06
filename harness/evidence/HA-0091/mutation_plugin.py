"""Opt-in, process-local HA91 probes; never changes shared production files."""
import os
import time

import pytest


@pytest.fixture(autouse=True)
def ha91_probe(request, monkeypatch):
    if request.node.name != 'test_cancel_while_provider_waits_never_publishes':
        return
    mode = os.environ.get('HA91_MUTATION')
    if mode == 'M1':
        from backend.dsh_runtime import DshRuntime
        monkeypatch.setattr(DshRuntime, 'cancel', lambda self, ident: None)
    elif mode == 'M2':
        import backend.dsh_runtime as runtime
        original = runtime.budgeted_model_call

        async def ignore_cancellation(*args, **kwargs):
            kwargs['cancel_event'] = None
            return await original(*args, **kwargs)

        monkeypatch.setattr(runtime, 'budgeted_model_call', ignore_cancellation)
    elif mode == 'C1':
        from adapters.dsh import DshAdapter
        original = DshAdapter.run

        def delayed_start(self, *args, **kwargs):
            # Simulate setup longer than the former 10-second assertion.
            # The actual SDK and Provider path still execute normally.
            time.sleep(11)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(DshAdapter, 'run', delayed_start)
    elif mode:
        raise ValueError('Unknown HA91 mutation')
