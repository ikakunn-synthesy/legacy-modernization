# legacy-modernization

販売・生産・会計のレガシー資産を段階的に移行するための業務バックエンドです。

## フェーズ1

- CSV・固定長ファイルを、宣言された文字コードから厳密にUTF-8へ変換して取込
- 変換履歴と移行例外を保存
- 得意先・品目の標準マスタと単価契約の版管理
- 販売・生産からの更新を追跡する共有在庫台帳

文字列の変換に失敗した場合、置換文字による継続はしません。取込を失敗として記録し、修正後の再処理対象にします。

## 開発

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export DATABASE_URL='postgresql+psycopg://legacy:legacy@localhost:5432/legacy_modernization'
uvicorn app.main:app --reload
pytest
```

PostgreSQLを使用します。`DATABASE_URL` を設定しない開発・テスト環境ではSQLiteを使用できます。
