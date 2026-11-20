from waitress import serve

from . import create_app


app = create_app()


if __name__ == "__main__":
    proxy = app.config["CHORES_TRUSTED_PROXY"]
    options = {}
    if proxy:
        options.update(trusted_proxy=proxy, trusted_proxy_count=1,
                       trusted_proxy_headers={"x-forwarded-proto"})
    serve(app, host=app.config["CHORES_HOST"], port=app.config["PORT"],
          clear_untrusted_proxy_headers=True, **options)
