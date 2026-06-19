import sys
import types


def _install_dotenv_stub():
    dotenv_module = types.ModuleType("dotenv")
    dotenv_module.load_dotenv = lambda *args, **kwargs: None
    sys.modules.setdefault("dotenv", dotenv_module)


def _install_groq_stub():
    groq_module = types.ModuleType("groq")

    class FakeCompletions:
        def create(self, **kwargs):
            message = types.SimpleNamespace(content="stub response")
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice])

    class FakeChat:
        completions = FakeCompletions()

    class FakeGroq:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.chat = FakeChat()

    groq_module.Groq = FakeGroq
    sys.modules.setdefault("groq", groq_module)


def _install_gradio_stub():
    gradio_module = types.ModuleType("gradio")

    def _component(*args, **kwargs):
        return {"args": args, "kwargs": kwargs}

    class _Context:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Button:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def click(self, *args, **kwargs):
            return None

    class _Textbox:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def submit(self, *args, **kwargs):
            return None

    gradio_module.Blocks = _Context
    gradio_module.Row = _Context
    gradio_module.Markdown = _component
    gradio_module.Textbox = _Textbox
    gradio_module.Radio = _component
    gradio_module.Button = _Button
    gradio_module.Examples = _component
    sys.modules.setdefault("gradio", gradio_module)


_install_dotenv_stub()
_install_groq_stub()
_install_gradio_stub()
