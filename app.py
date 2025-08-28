import json
import pandas as pd
import streamlit as st
import altair as alt
from pathlib import Path
import re
import collections
import itertools

# ページ設定
st.set_page_config(
    page_title="国会ダッシュボード",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS：翻訳・縦書き化を無効化（SVGテキストのズレ防止）+ デザイン改善
st.markdown("""
<style>
/* Google 翻訳が SVG テキストをいじらないように */
.notranslate, .vega-embed, .vega-embed * { 
  unicode-bidi: plaintext; 
}
.vega-embed svg text {
  writing-mode: horizontal-tb !important;
  direction: ltr !important;
}
/* ラベルを省略しない */
.vega-embed .role-axis-label { text-overflow: clip !important; }

/* メインタイトルのスタイリング */
.main-header {
    background: linear-gradient(90deg, #1f4e79, #2e5c8a);
    color: white;
    padding: 1.5rem;
    border-radius: 10px;
    margin-bottom: 2rem;
    text-align: center;
}

/* メトリクスのスタイリング */
.metric-container {
    background: #f8f9fa;
    padding: 1rem;
    border-radius: 8px;
    border-left: 4px solid #1f4e79;
}

/* サイドバーのスタイリング */
.sidebar .sidebar-content {
    background: #f8f9fa;
}

/* エラー・警告メッセージのカスタマイズ */
.stAlert {
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)

# Altair の軸を水平に固定 & 省略無し + 日本語対応
alt.themes.register('jp_fix', lambda: {
    "config": {
        "axis": {
            "labelAngle": 0, 
            "labelLimit": 0,  # ラベル省略を無効化
            "labelFontSize": 10,
            "titleFontSize": 12,
            "grid": True,
            "tickSize": 5
        },
        "header": {"labelAngle": 0},
        "view": {"strokeWidth": 0},  # 枠線を削除
        "legend": {
            "labelFontSize": 10,
            "titleFontSize": 12
        },
        "title": {
            "fontSize": 14,
            "fontWeight": "bold"
        }
    }
})
alt.themes.enable('jp_fix')

# メインタイトル
st.markdown("""
<div class="main-header">
    <h1>🏛️ 国会ダッシュボード</h1>
    <p>国会会議録から議論の全体像を可視化(現在25/1/23~8/5のみ対応)</p>
</div>
""", unsafe_allow_html=True)

DATA_DIR = Path(__file__).parent / "data"

@st.cache_data
def load_data():
    """データ読み込み関数"""
    try:
        speeches = pd.read_csv(DATA_DIR / "speeches_sample.csv")
        
        # データクレンジング
        speeches["date"] = pd.to_datetime(speeches["date"], errors="coerce")
        
        # 文字数計算
        if "speech" in speeches.columns:
            speeches["char_count"] = speeches["speech"].fillna("").astype(str).apply(len)
        else:
            speeches["char_count"] = 0
        
        # 欠損列の補完
        required_columns = ["speechURL", "meetingURL", "issueID", "billID", 
                          "speakerGroup", "nameOfHouse", "nameOfMeeting"]
        for col in required_columns:
            if col not in speeches.columns:
                speeches[col] = None
        
        # 表記統一
        speeches["party"] = speeches["speakerGroup"].fillna("政党不明")
        speeches["house"] = speeches["nameOfHouse"].fillna("院不明")
        speeches["committee"] = speeches["nameOfMeeting"].fillna("委員会不明")
        speeches["speaker"] = speeches["speaker"].fillna("発言者不明")
        
        return speeches
    
    except FileNotFoundError:
        st.error("❌ データファイルが見つかりません。data/speeches_sample.csv を確認してください。")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ データ読み込みエラー: {str(e)}")
        return pd.DataFrame()

def extract_keywords(text: str, min_length: int = 2, max_length: int = 6) -> list[str]:
    """キーワード抽出関数（改良版）"""
    if not isinstance(text, str) or not text.strip():
        return []
    
    # 漢字とカタカナの抽出（長さ制限付き）
    kanji_pattern = rf'[\u4E00-\u9FFF]{{{min_length},{max_length}}}'
    kata_pattern = rf'[ァ-ヴー]{{{min_length + 1},}}'
    
    kanji_terms = re.findall(kanji_pattern, text)
    kata_terms = re.findall(kata_pattern, text)
    
    # ストップワード（拡張版）
    stop_words = {
        '委員会', '本会議', '政府', '総理', '大臣', '答弁', '質疑', '報告', '資料', 
        '法律', '制度', '今回', '我が国', '国会', '議員', '先生', '委員', '議論',
        '問題', '課題', '対応', '検討', '実施', '推進', '確認', '説明', '質問'
    }
    
    # フィルタリング
    all_terms = kanji_terms + kata_terms
    filtered_terms = [term for term in all_terms if term not in stop_words]
    
    return filtered_terms

def create_heatmap_data(df: pd.DataFrame, top_terms: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    """ヒートマップ用データ作成"""
    if len(top_terms) == 0:
        return pd.DataFrame()
    
    focus_terms = set(top_terms['term'].head(top_n))
    
    # 政党×キーワードの出現回数を集計
    heatmap_rows = []
    for party, group in df.groupby('party'):
        party_terms = []
        for speech in group['speech'].fillna(''):
            party_terms.extend([term for term in extract_keywords(speech) if term in focus_terms])
        
        term_counts = collections.Counter(party_terms)
        for term, count in term_counts.items():
            heatmap_rows.append({'party': party, 'term': term, 'count': count})
    
    if not heatmap_rows:
        return pd.DataFrame()
    
    heat_df = pd.DataFrame(heatmap_rows)
    
    # 順序を決定（頻度順）
    term_order = (heat_df.groupby('term')['count'].sum()
                 .sort_values(ascending=False).index.tolist())
    party_order = (heat_df.groupby('party')['count'].sum()
                  .sort_values(ascending=False).index.tolist())
    
    # 全組み合わせのマトリックス作成（0埋め）
    complete_data = []
    for party in party_order:
        for term in term_order:
            count = heat_df[(heat_df['party'] == party) & (heat_df['term'] == term)]['count'].sum()
            complete_data.append({'party': party, 'term': term, 'count': count})
    
    return pd.DataFrame(complete_data)

def truncate_labels(labels: list, max_length: int = 8) -> list:
    """ラベルを指定文字数で切り詰める"""
    return [label[:max_length] + "..." if len(label) > max_length else label for label in labels]

def create_readable_chart(data: pd.DataFrame, chart_type: str = "bar", **kwargs) -> alt.Chart:
    """読みやすいチャートを作成するユーティリティ関数"""
    if chart_type == "horizontal_bar":
        return alt.Chart(data).mark_bar().encode(
            x=alt.X(kwargs.get('x'), title=kwargs.get('x_title')),
            y=alt.Y(kwargs.get('y'), 
                   title=kwargs.get('y_title'),
                   sort=kwargs.get('sort', '-x'),
                   axis=alt.Axis(labelLimit=200, labelFontSize=10)),
            color=kwargs.get('color'),
            tooltip=kwargs.get('tooltip')
        ).properties(
            height=kwargs.get('height', 400),
            width=kwargs.get('width', 600)
        )
    
    return alt.Chart(data)

# データ読み込み
speeches = load_data()

if speeches.empty:
    st.stop()

# =========================
# サイドバー：フィルタ設定
# =========================
with st.sidebar:
    st.header("🔍 フィルタ設定")
    
    # 日付フィルタ
    if not speeches["date"].isna().all():
        date_min = speeches["date"].min().date()
        date_max = speeches["date"].max().date()
        date_range = st.date_input(
            "📅 期間選択", 
            value=(date_min, date_max),
            min_value=date_min,
            max_value=date_max
        )
    else:
        st.warning("日付データが不正です")
        date_range = None
    
    # 院フィルタ
    available_houses = sorted([h for h in speeches["house"].unique() if h and h != "院不明"])
    if available_houses:
        houses = st.multiselect(
            "🏛️ 院選択", 
            options=available_houses,
            default=available_houses
        )
    else:
        houses = []
    
    # 委員会フィルタ
    available_committees = sorted([c for c in speeches["committee"].unique() 
                                 if c and c != "委員会不明"])[:20]  # 表示を20個に制限
    if available_committees:
        committees = st.multiselect(
            "📋 委員会選択", 
            options=available_committees,
            default=available_committees
        )
    else:
        committees = []
    
    # キーワードフィルタ
    keyword_input = st.text_input(
        "🔎 キーワード検索", 
        value="",
        placeholder="例: 税制 消費税（スペース区切り）",
        help="空欄の場合は全件対象"
    )
    
    st.markdown("---")
    st.markdown("### 📊 表示設定")
    show_debug_info = st.checkbox("デバッグ情報を表示", value=False)
    
    # グラフ表示オプション
    st.markdown("### 🎨 グラフオプション")
    chart_height = st.slider("チャート高さ", min_value=300, max_value=800, value=500, step=50)
    use_horizontal_layout = st.checkbox("長いラベルは横棒グラフで表示", value=True)
    max_items_display = st.slider("最大表示項目数", min_value=10, max_value=50, value=20, step=5)

# =========================
# データフィルタリング
# =========================
filtered_df = speeches.copy()

# 日付フィルタ適用
if date_range and len(date_range) == 2:
    filtered_df = filtered_df[
        (filtered_df["date"] >= pd.to_datetime(date_range[0])) & 
        (filtered_df["date"] <= pd.to_datetime(date_range[1]))
    ]

# 院フィルタ適用
if houses:
    filtered_df = filtered_df[filtered_df["house"].isin(houses)]

# 委員会フィルタ適用
if committees:
    filtered_df = filtered_df[filtered_df["committee"].isin(committees)]

# キーワードフィルタ適用
if keyword_input.strip():
    keywords = [k.strip() for k in keyword_input.split() if k.strip()]
    pattern = "|".join(map(re.escape, keywords))
    filtered_df = filtered_df[
        filtered_df["speech"].fillna("").str.contains(pattern, regex=True, case=False)
    ]

# =========================
# メトリクス表示
# =========================
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("📝 総発言数", f"{len(filtered_df):,}件")

with col2:
    if not filtered_df.empty:
        unique_speakers = filtered_df["speaker"].nunique()
        st.metric("👥 発言者数", f"{unique_speakers:,}人")
    else:
        st.metric("👥 発言者数", "0人")

with col3:
    if not filtered_df.empty:
        total_chars = filtered_df["char_count"].sum()
        st.metric("📊 総文字数", f"{total_chars:,}文字")
    else:
        st.metric("📊 総文字数", "0文字")

with col4:
    if not filtered_df.empty:
        unique_parties = filtered_df["party"].nunique()
        st.metric("🏢 政党数", f"{unique_parties:,}")
    else:
        st.metric("🏢 政党数", "0")

# データが空の場合の処理
if filtered_df.empty:
    st.warning("⚠️ 選択された条件に該当するデータがありません。フィルタ条件を見直してください。")
    st.stop()

st.markdown("---")

# =========================
# キーワード分析セクション
# =========================
st.header("🔤 議論されているキーワード")

# キーワード抽出
with st.spinner("キーワードを分析中..."):
    all_keywords = []
    for speech in filtered_df['speech'].fillna(''):
        all_keywords.extend(extract_keywords(speech))
    
    # 頻出キーワードTop30
    keyword_counter = collections.Counter(all_keywords)
    top_keywords = pd.DataFrame(
        keyword_counter.most_common(30), 
        columns=['term', 'count']
    )

if len(top_keywords) > 0:
    # 2列レイアウト
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📈 頻出キーワード Top30")
        keyword_chart = alt.Chart(top_keywords.head(20)).mark_bar().encode(
            x=alt.X('count:Q', title='出現回数'),
            y=alt.Y('term:N', sort='-x', title='キーワード'),
            color=alt.Color('count:Q', scale=alt.Scale(scheme='blues')),
            tooltip=['term:N', 'count:Q']
        ).properties(
            height=500
        )
        st.altair_chart(keyword_chart, use_container_width=True)
    
    with col2:
        st.subheader("🎯 キーワード詳細")
        if len(top_keywords) > 0:
            selected_term = st.selectbox(
                "詳細を見るキーワードを選択",
                options=top_keywords['term'].head(10).tolist(),
                index=0
            )
            
            # 選択されたキーワードの使用例
            examples = filtered_df[
                filtered_df['speech'].fillna('').str.contains(
                    re.escape(selected_term), regex=True
                )
            ].sort_values('date', ascending=False)
            
            st.markdown(f"**キーワード「{selected_term}」の使用例:**")
            for idx, row in examples.head(3).iterrows():
                # 発言の一部を抜粋
                speech_text = str(row['speech'])
                if len(speech_text) > 150:
                    speech_text = speech_text[:150] + "..."
                
                st.markdown(f"""
                **{row['speaker']}** ({row['party']}) - {row['date'].strftime('%Y-%m-%d')}  
                "{speech_text}"
                """)
    
    # ヒートマップ（政党×キーワード）
    st.subheader("🔥 政党×主要キーワード ヒートマップ")
    
    heatmap_data = create_heatmap_data(filtered_df, top_keywords, top_n=15)
    
    if len(heatmap_data) > 0:
        if show_debug_info:
            with st.expander("🐛 ヒートマップ デバッグ情報"):
                st.write(f"ヒートマップデータ行数: {len(heatmap_data)}")
                st.write(f"キーワード数: {heatmap_data['term'].nunique()}")
                st.write(f"政党数: {heatmap_data['party'].nunique()}")
                st.dataframe(heatmap_data.head(10))
        
        # キーワードと政党の順序を決定
        term_order = (heatmap_data.groupby('term')['count'].sum()
                     .sort_values(ascending=False).index.tolist())
        party_order = (heatmap_data.groupby('party')['count'].sum()
                      .sort_values(ascending=False).index.tolist())
        
        # ヒートマップのサイズとレイアウトを改善
        max_term_length = max([len(term) for term in term_order]) if term_order else 0
        max_party_length = max([len(party) for party in party_order]) if party_order else 0
        
        # キーワード数が多い場合は表示数を制限
        if len(term_order) > 20:
            term_order = term_order[:20]
            heatmap_data = heatmap_data[heatmap_data['term'].isin(term_order)]
            st.info("⚠️ キーワード数が多いため、上位20個のみ表示しています")
        
        heatmap_chart = alt.Chart(heatmap_data).mark_rect(stroke='white', strokeWidth=1).encode(
            x=alt.X('term:O', 
                   title='キーワード',
                   sort=term_order,
                   axis=alt.Axis(
                       labelAngle=-45 if max_term_length > 3 else 0,
                       labelLimit=0,
                       labelFontSize=9,
                       titleFontSize=12
                   )),
            y=alt.Y('party:O', 
                   title='政党',
                   sort=party_order,
                   axis=alt.Axis(
                       labelLimit=0,
                       labelFontSize=9,
                       titleFontSize=12
                   )),
            color=alt.Color('count:Q', 
                          title='発言頻度',
                          scale=alt.Scale(
                              type='sqrt',
                              range=['#f7f7f7', '#2166ac']
                          )),
            tooltip=[
                alt.Tooltip('party:N', title='政党'),
                alt.Tooltip('term:N', title='キーワード'),
                alt.Tooltip('count:Q', title='頻度')
            ]
        ).properties(
            width=max(600, len(term_order) * 40),
            height=max(300, len(party_order) * 35)
        ).resolve_scale(
            color='independent'
        )
        
        st.altair_chart(heatmap_chart, use_container_width=True)
    else:
        st.info("ℹ️ ヒートマップ用のデータが不足しています。")

else:
    st.info("ℹ️ キーワードが抽出できませんでした。データの内容やフィルタ条件を確認してください。")

st.markdown("---")

# =========================
# 発言量分析セクション
# =========================
st.header("📊 発言量分析")

col1, col2 = st.columns(2)

with col1:
    st.subheader("👤 議員別発言量 Top20")
    if not filtered_df.empty:
        speaker_ranking = (
            filtered_df.groupby(["speaker", "party"], as_index=False)["char_count"]
            .sum()
            .sort_values("char_count", ascending=False)
            .head(20)
        )
        
        speaker_chart = alt.Chart(speaker_ranking).mark_bar().encode(
            x=alt.X("char_count:Q", title="発言文字数"),
            y=alt.Y("speaker:N", sort='-x', title="議員名"),
            color=alt.Color("party:N", title="政党", scale=alt.Scale(scheme='category20')),
            tooltip=["speaker:N", "party:N", "char_count:Q"]
        ).properties(height=500)
        
        st.altair_chart(speaker_chart, use_container_width=True)
    else:
        st.info("データがありません")

with col2:
    st.subheader("🏢 政党別発言数")
    if not filtered_df.empty:
        party_stats = (
            filtered_df.groupby("party", as_index=False)
            .agg({
                "speech": "count",
                "char_count": "sum"
            })
            .rename(columns={"speech": "speech_count"})
            .sort_values("speech_count", ascending=False)
        )
        
        # 政党名が長い場合は横棒グラフに変更
        if len(party_stats) > 8 or party_stats['party'].str.len().max() > 6:
            party_chart = alt.Chart(party_stats).mark_bar().encode(
                x=alt.X("speech_count:Q", title="発言数"),
                y=alt.Y("party:O", title="政党", sort="-x", 
                       axis=alt.Axis(labelLimit=200, labelFontSize=10)),
                color=alt.Color("speech_count:Q", scale=alt.Scale(scheme='viridis')),
                tooltip=["party:N", "speech_count:Q", "char_count:Q"]
            ).properties(height=max(400, len(party_stats) * 30))
        else:
            party_chart = alt.Chart(party_stats).mark_bar().encode(
                x=alt.X("party:N", title="政党", 
                       axis=alt.Axis(labelAngle=-45, labelLimit=0, labelFontSize=10)),
                y=alt.Y("speech_count:Q", title="発言数"),
                color=alt.Color("speech_count:Q", scale=alt.Scale(scheme='viridis')),
                tooltip=["party:N", "speech_count:Q", "char_count:Q"]
            ).properties(height=500)
        
        st.altair_chart(party_chart, use_container_width=True)
    else:
        st.info("データがありません")

# 時系列分析
st.subheader("📈 発言数の推移（日別）")
if not filtered_df.empty and not filtered_df["date"].isna().all():
    daily_stats = (
        filtered_df.groupby("date", as_index=False)
        .agg({
            "speech": "count",
            "char_count": "sum"
        })
        .rename(columns={"speech": "speech_count"})
    )
    
    timeline_chart = alt.Chart(daily_stats).mark_line(point=True).encode(
        x=alt.X("date:T", title="日付"),
        y=alt.Y("speech_count:Q", title="発言数"),
        tooltip=["date:T", "speech_count:Q", "char_count:Q"]
    ).properties(height=300)
    
    st.altair_chart(timeline_chart, use_container_width=True)
else:
    st.info("ℹ️ 日付データが不足しているため時系列分析をスキップします")

st.markdown("---")

# =========================
# 最新発言セクション
# =========================
st.header("📰 最新の発言")

if not filtered_df.empty:
    latest_speeches = (
        filtered_df.sort_values("date", ascending=False)
        .head(20)
        [["date", "house", "committee", "speaker", "party", "speech"]]
        .copy()
    )
    
    # 発言を適切な長さに切り詰め
    latest_speeches["speech"] = (
        latest_speeches["speech"]
        .fillna("")
        .astype(str)
        .apply(lambda x: (x[:200] + "...") if len(x) > 200 else x)
    )
    
    # 日付を読みやすい形式に変換
    latest_speeches["date"] = latest_speeches["date"].dt.strftime("%Y-%m-%d")
    
    st.dataframe(
        latest_speeches, 
        use_container_width=True,
        column_config={
            "date": "日付",
            "house": "院",
            "committee": "委員会",
            "speaker": "発言者",
            "party": "政党",
            "speech": "発言内容"
        }
    )
else:
    st.info("表示する発言がありません")

# =========================
# フッター
# =========================
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 2rem;'>
    <p>📊 <strong>国会ダッシュボード</strong> | データソース: 国会会議録検索システム API</p>
    <p>🔧 プロトタイプ版 | より詳細な分析機能は随時追加予定</p>
</div>
""", unsafe_allow_html=True)