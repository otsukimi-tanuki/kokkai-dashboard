
# 国会ダッシュボード（試作キット）

議事録の横串可視化を試すためのプロトタイプです。  
データへの差し替えは `fetch_kokkai.py` を利用してください。(こちらも試作版)

## セットアップ
```bash
pip install -r requirements.txt
streamlit run app.py
```

## フォルダ構成
- `app.py` : Streamlit のダッシュボード本体
- `data/` : CSV（`speeches_sample.csv`）
- `fetch_kokkai.py` : 国会会議録検索システム API から発言を取得する簡易スクリプト（試作）



## ライセンス
- コード: MIT
- データ: 出典を明記のうえ国会会議録検索システム等の条件に従ってください。
