from colab_cli.commands.uv_prompt import parse_accelerator_choice, prompt_accelerator


def test_parse_accelerator_choice_gpus():
    assert parse_accelerator_choice("1") == ("g4", None, False)
    assert parse_accelerator_choice("g4") == ("g4", None, False)
    assert parse_accelerator_choice("2") == ("a100", None, False)
    assert parse_accelerator_choice("a100") == ("a100", None, False)
    assert parse_accelerator_choice("3") == ("l4", None, False)
    assert parse_accelerator_choice("4") == ("t4", None, False)
    assert parse_accelerator_choice("5") == ("h100", None, False)


def test_parse_accelerator_choice_tpus():
    assert parse_accelerator_choice("v6e-1") == (None, "v6e1", False)
    assert parse_accelerator_choice("v5e1") == (None, "v5e1", False)


def test_parse_accelerator_choice_default_no_gpu():
    # Never defaults to any GPU
    assert parse_accelerator_choice("") == (None, None, False)
    assert parse_accelerator_choice("unknown_val") == (None, None, False)


def test_parse_accelerator_choice_cpu():
    assert parse_accelerator_choice("6", high_ram_choice="n") == (None, None, False)
    assert parse_accelerator_choice("none", high_ram_choice="y") == (None, None, True)
    assert parse_accelerator_choice("cpu", high_ram_choice="yes") == (None, None, True)


def test_prompt_accelerator_mocked_input(monkeypatch):
    inputs = iter(["2", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    gpu, tpu, high_mem = prompt_accelerator()
    assert gpu == "a100"
    assert tpu is None
    assert high_mem is False


def test_prompt_accelerator_cpu_high_mem(monkeypatch):
    inputs = iter(["6", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    gpu, tpu, high_mem = prompt_accelerator()
    assert gpu is None
    assert tpu is None
    assert high_mem is True


