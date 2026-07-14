"""moomoo OpenDへの接続確認。"""

from moomoo import RET_OK, OpenQuoteContext


def main() -> None:
    """OpenDへ接続し、接続状態を確認する。"""

    quote_context = OpenQuoteContext(
        host="127.0.0.1",
        port=11111,
    )

    try:
        return_code, data = quote_context.get_global_state()

        if return_code != RET_OK:
            print("OpenD接続後の情報取得に失敗しました。")
            print(data)
            return

        print("=" * 50)
        print("moomoo OpenD connection successful")
        print("=" * 50)
        print(data)

    finally:
        quote_context.close()


if __name__ == "__main__":
    main()
