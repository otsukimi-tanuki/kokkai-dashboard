
# -*- coding: utf-8 -*-
"""
国会会議録 取得ツール（GUI） v1.0
- meeting_list: トップ直下 `meetingRecord` を抽出
- speech: トップ直下 `speechRecord` を抽出
- CSV ダウンロードは UTF-8 (BOM 付き) で文字化け回避
"""
import streamlit as st
import pandas as pd
import requests, time, json
from datetime import date

SPEECH_URL = "https://kokkai.ndl.go.jp/api/speech"
MEETING_LIST_URL = "https://kokkai.ndl.go.jp/api/meeting_list"
UA = "kokkai-dashboard-gui-fetcher/1.0"

st.set_page_config(page_title="国会データ取得GUI", layout="wide")
st.title("国会会議録 取得ツール（GUI）")
st.caption("一次情報：国会会議録検索システム API")

def build_params(date_from, date_until, house, committee, kw_terms, mode, start=1, maximum=100, include_keywords=True):
    p = dict(recordPacking="json", maximumRecords=maximum, startRecord=start, from_=date_from, until=date_until)
    p["from"] = p.pop("from_")
    if committee:
        p["nameOfMeeting"] = committee
    if house and house != "両院":
        p["nameOfHouse"] = house
    if include_keywords and kw_terms:
        if mode.startswith("AND"):
            p["any"] = " ".join(kw_terms)
        else:
            p["any"] = kw_terms[0]  # OR の場合は語ごとにループ
    return p

def num_records(js):
    if isinstance(js, dict) and "numberOfRecords" in js:
        try: return int(js["numberOfRecords"])
        except: return js["numberOfRecords"]
    if isinstance(js, dict) and "records" in js and isinstance(js["records"], dict):
        n = js["records"].get("numberOfRecords")
        try: return int(n)
        except: return n
    return None

with st.sidebar:
    st.header("検索条件")
    c1, c2 = st.columns(2)
    date_from = c1.date_input("開始日", value=date(2024, 1, 1))
    date_until = c2.date_input("終了日", value=date.today())
    houses = st.multiselect("院（複数可）", options=["衆議院", "参議院", "両院"], default=["両院"])
    mode = st.selectbox("キーワードの一致方法", options=["AND（すべて含む）","OR（いずれか含む）","なし（全文対象）"], index=1)
    kw = st.text_input("キーワード（スペース区切り）", value="消費税 税制 外国")
    endpoint = st.radio("エンドポイント", options=["speech（発言単位）","meeting_list（会議簡易）"], index=1)
    outname = st.text_input("保存ファイル名（CSV）", value="speeches_or_meetings.csv")

st.divider()
run = st.button("取得してCSVを作成")

def fetch(date_from, date_until, houses, committees, kw, mode, all_committees, endpoint="speech"):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    terms = [t for t in (kw or "").split() if t.strip()]
    if mode.startswith("なし"):
        terms = []
    df_all = []
    last_params = {}
    last_url = ""
    last_num = None
    last_preview = ""

    houses = houses or ["両院"]
    committees = committees or [None]
    if all_committees:
        committees = [None]

    for h in houses:
        for cm in committees:
            if endpoint.startswith("meeting"):
                # meeting_list: any は使わない
                start = 1
                while True:
                    p = build_params(str(date_from), str(date_until), h, cm, [], mode, start=start, maximum=100, include_keywords=False)
                    r = requests.get(MEETING_LIST_URL, params=p, headers=headers, timeout=60)
                    last_params = p; last_url = r.url
                    r.raise_for_status()
                    js = r.json()
                    last_num = num_records(js)
                    recs = js.get("meetingRecord") or []
                    if not recs:
                        last_preview = json.dumps(js, ensure_ascii=False)[:800]
                        break
                    rows = []
                    for mt in recs:
                        sp_recs = mt.get("speechRecord") or []
                        url = sp_recs[0].get("speechURL") if isinstance(sp_recs, list) and len(sp_recs) else None
                        rows.append({
                            "date": mt.get("date"),
                            "house": mt.get("nameOfHouse"),
                            "meeting": mt.get("nameOfMeeting"),
                            "issue": mt.get("issue"),
                            "session": mt.get("session"),
                            "url": url,
                        })
                    df_all.append(pd.DataFrame(rows))
                    if len(recs) < 100:
                        break
                    start += len(recs)
                    time.sleep(0.5)
            else:
                # speech: AND はまとめ / OR は語ごと
                term_sets = [terms] if (terms and mode.startswith("AND")) else [[t] for t in terms] if terms else [[]]
                for ts in term_sets:
                    start = 1
                    while True:
                        p = build_params(str(date_from), str(date_until), h, cm, ts, "AND", start=start, maximum=100, include_keywords=True)
                        r = requests.get(SPEECH_URL, params=p, headers=headers, timeout=60)
                        last_params = p; last_url = r.url
                        r.raise_for_status()
                        js = r.json()
                        last_num = num_records(js)
                        recs = js.get("speechRecord") or []
                        if not recs:
                            last_preview = json.dumps(js, ensure_ascii=False)[:800]
                            break
                        rows = []
                        for sp in recs:
                            rows.append({
                                "speech_id": sp.get("speechID"),
                                "date": sp.get("date"),
                                "nameOfHouse": sp.get("nameOfHouse") or sp.get("houseName"),
                                "nameOfMeeting": sp.get("nameOfMeeting"),
                                "speaker": sp.get("speaker"),
                                "speakerGroup": sp.get("speakerGroup"),
                                "speech": sp.get("speech"),
                                "speechURL": sp.get("speechURL"),
                                "issueID": sp.get("issueID"),
                                "meetingURL": sp.get("meetingURL"),
                                "billID": sp.get("billID"),
                            })
                        df_all.append(pd.DataFrame(rows))
                        if len(recs) < 100:
                            break
                        start += len(recs)
                        time.sleep(1.0)

    df = pd.concat(df_all, ignore_index=True) if df_all else pd.DataFrame()
    if len(df) and "speech_id" in df.columns:
        df = df.drop_duplicates(subset=["speech_id"])
    return df, last_params, last_url, last_num, last_preview

if run:
    with st.spinner("取得中..."):
        df, last_params, last_url, last_num, last_preview = fetch(date_from, date_until, houses, [], kw, mode, all_committees, endpoint="speech" if endpoint.startswith("speech") else "meeting_list")
    st.success(f"取得件数: {len(df)}")
    with st.expander("デバッグ情報"):
        st.write("最後に実行したURL："); st.code(last_url or "(なし)")
        st.write("最後のクエリパラメータ："); st.json(last_params or {})
        if last_num is not None: st.write(f"numberOfRecords: {last_num}")
        if len(df)==0 and last_preview:
            st.write("Raw JSON preview (truncated):"); st.code(last_preview)
    if len(df):
        # Excel でも文字化けしない BOM 付き UTF-8
        csv_text = df.to_csv(index=False, encoding="utf-8-sig")
        csv_bytes = csv_text.encode("utf-8-sig")
        st.download_button("CSVをダウンロード", data=csv_bytes, file_name=outname, mime="text/csv")
        st.dataframe(df.head(30))
    else:
        st.info("0件。meeting_list は any 不使用。period/filters を緩め、speech は複合語×ORで。")
