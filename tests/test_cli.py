from smhelper import main


def test_main_prints_greeting(capsys) -> None:
    main()

    assert capsys.readouterr().out == "Hello from smhelper!\n"
