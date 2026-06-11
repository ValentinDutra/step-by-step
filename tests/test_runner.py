from app.runner import PipelineRunnerMixin


class _FakeBar:
    def update(self, *args):
        pass

    def remove_class(self, *args):
        pass

    def add_class(self, *args):
        pass


class _FakeInput:
    disabled = True


class _Stub(PipelineRunnerMixin):
    def __init__(self, working_dir):
        self.working_dir = working_dir
        self.config_path = ""
        self.running = True
        self.logs = []

    def _write_log(self, message):
        self.logs.append(message)


def test_resolve_or_report_aborts_on_invalid_config(tmp_path):
    (tmp_path / "step-by-step.toml").write_text('[defaults]\nprovider="nope"\n')
    stub = _Stub(str(tmp_path))
    bar, prompt_input = _FakeBar(), _FakeInput()

    result = stub._resolve_or_report(bar, prompt_input)

    assert result is None  # invalid config does not raise; it reports and aborts
    assert stub.running is False
    assert prompt_input.disabled is False
