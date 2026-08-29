# legacy-modernization

販売・生産・会計のレガシー資産を段階的に移行するための業務バックエンドです。

## フェーズ1

- CSV・固定長ファイルを、宣言された文字コードから厳密にUTF-8へ変換して取込
- 元ファイルのバイト列、文字コード、行ごとの変換履歴、移行例外をPostgreSQLへ保存
- 得意先・品目の標準マスタと単価契約の版管理
- 販売・生産からの更新で元在庫区分も保持する共有在庫台帳

文字列の変換に失敗した場合、置換文字による継続はしません。取込を失敗として記録し、修正後の再処理対象にします。

## 開発

```bash
cp .env.example .env
docker compose up -d postgres
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
pytest
```

PostgreSQLが必須です。`DATABASE_URL` を設定してからアプリケーションまたはテストを開始してください。
