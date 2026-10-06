import inspect
import os
import textwrap


def pytest_configure(config):
    import backend.dsh_runtime as dsh
    import backend.service as service
    mode = os.environ['HA89_MUTATION']
    if mode in ('M2', 'C2'):
        module, cls, method = service, service.Service, 'check'
        old, new = "if age >= run['effective_limits']['timeout_seconds']:", "if False:"
    else:
        module, cls, method = dsh, dsh.DshRuntime, 'execute'
        old, new = (
            ('if time.monotonic() >= deadline:', 'if False:') if mode == 'M1' else
            ('timeout_seconds=min(self.provider_timeout_seconds, max(.1, deadline-time.monotonic()))',
             'timeout_seconds=max(.1, deadline-time.monotonic())'))
    if mode == 'C2':
        new = old  # Identity-compile control, retaining live module globals.
    source = textwrap.dedent(inspect.getsource(getattr(cls, method)))
    assert source.count(old) == 1
    # Preserve live module globals so the test's local clock injection still
    # reaches the mutant; a copied dictionary would confound the deadline test.
    namespace = vars(module)
    exec(compile(source.replace(old, new), module.__file__, 'exec'), namespace)
    setattr(cls, method, namespace[method])
