TEST_PASSWORD = "senha-teste-12345"


def login(app):
    app.run()
    assert not app.exception
    app.text_input(key="login_password").set_value(TEST_PASSWORD)
    next(button for button in app.button if button.label == "Entrar").click().run()
    assert not app.exception
    return app
