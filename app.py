import streamlit as st
import json
import re
import csv
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date, time

# ===== メール送信設定 =====
SMTP_SERVER = "mail.heteml.jp"
SMTP_PORT = 587
SMTP_USER = st.secrets.get("SMTP_USER", "info_purchase@revise.co.jp")
SMTP_PASSWORD = st.secrets.get("SMTP_PASSWORD", "")
SENDER_NAME = "マイくるサポートセンター"
SENDER_EMAIL = SMTP_USER

def send_email(to_address, subject, body):
    """SMTPでメールを送信し、IMAPで送信済みフォルダに保存する"""
    try:
        import imaplib
        from email.header import Header
        from email.utils import formataddr
        from datetime import datetime as dt
        
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = formataddr((str(Header(SENDER_NAME, "utf-8")), SENDER_EMAIL))
        msg["To"] = to_address
        msg["Subject"] = Header(subject, "utf-8")
        msg["Date"] = dt.now().strftime("%a, %d %b %Y %H:%M:%S +0900")
        
        msg_string = msg.as_string()
        
        # SMTP送信
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, local_hostname="localhost") as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_address, msg_string)
        
        # IMAP接続して送信済みフォルダに保存
        try:
            imap = imaplib.IMAP4_SSL("mail.heteml.jp", 993)
            imap.login(SMTP_USER, SMTP_PASSWORD)
            # 送信済みフォルダに保存（hetemlの場合は"Sent"または"INBOX.Sent"）
            sent_folder = "Sent"
            try:
                imap.append(sent_folder, "\\Seen", None, msg_string.encode("utf-8"))
            except:
                # フォルダ名が異なる場合の代替
                try:
                    imap.append("INBOX.Sent", "\\Seen", None, msg_string.encode("utf-8"))
                except:
                    imap.append("INBOX.sent", "\\Seen", None, msg_string.encode("utf-8"))
            imap.logout()
        except Exception as imap_err:
            # IMAP保存に失敗してもメール送信自体は成功しているので、警告のみ
            return True, f"送信成功（※送信済みフォルダへの保存に失敗：{str(imap_err)}）"
        
        return True, "送信成功"
    except Exception as e:
        return False, str(e)

# ===== データ読み込み =====
@st.cache_data
def load_triggers():
    with open("triggers.json", "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def load_templates():
    with open("templates.json", "r", encoding="utf-8") as f:
        return json.load(f)

TRIGGERS = load_triggers()
TEMPLATES = load_templates()

# オンライン手段と参加URLのマッピング
ONLINE_METHODS = {
    "電話": "",
    "ZOOM": "https://zoom.us/j/95098136147?pwd=53baBmF5ML3fD42i8pyLHQxcU1s4nS.1",
    "GoogleMeet": "https://meet.google.com/vuf-yieo-wjq"
}

# 時間帯の選択肢
TIME_SLOTS = [
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    "12:00", "12:30", "13:00", "13:30", "14:00", "14:30",
    "15:00", "15:30", "16:00", "16:30", "17:00", "17:30",
    "18:00", "18:30", "19:00", "19:30", "20:00"
]

# ===== テンプレートエンジン =====
def fill_template(template_id, variables):
    if template_id not in TEMPLATES:
        return None, None
    tmpl = TEMPLATES[template_id]
    subject = tmpl["subject"]
    body = tmpl["body"]
    for key, value in variables.items():
        subject = subject.replace(f"{{{{{key}}}}}", str(value))
        body = body.replace(f"{{{{{key}}}}}", str(value))
    return subject, body

def analyze_incoming_email(email_text):
    keywords_map = {
        "A-3": ["商談", "予約", "確認", "日程"],
        "A-12": ["書類", "返送", "郵送", "届"],
        "A-6": ["契約", "手続き", "フォーム", "入力"],
        "A-10": ["陸送", "引き上げ", "引取", "日程", "候補"],
        "A-16": ["日程", "確定", "決まり"],
        "A-22": ["検討", "まだ", "考え中"],
        "A-24": ["支払", "振込", "入金"],
    }
    scores = {}
    for tid, keywords in keywords_map.items():
        score = sum(1 for kw in keywords if kw in email_text)
        if score > 0:
            scores[tid] = score
    if scores:
        return max(scores, key=scores.get)
    return None

def save_log(trigger_name, customer_name, email_to, subject, status):
    log_file = "send_log.csv"
    file_exists = os.path.exists(log_file)
    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["送信日時", "トリガー名", "顧客名", "宛先", "件名", "ステータス"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            trigger_name, customer_name, email_to, subject, status
        ])

# ===== カスタム入力UI =====
def render_trigger_inputs(trigger):
    variables = {}
    
    col1, col2 = st.columns(2)
    with col1:
        customer_name = st.text_input("顧客名", key="customer_name", placeholder="例：山田太郎")
    with col2:
        email_to = st.text_input("送信先メールアドレス", key="email_to", placeholder="例：yamada@example.com")
    
    variables["顧客名"] = customer_name
    tid = trigger["template_id"]
    
    if tid in ["A-2", "A-3"]:
        st.caption("▼ 商談情報")
        col_a, col_b = st.columns(2)
        with col_a:
            selected_date = st.date_input("予約日", value=date.today(), key="booking_date", format="YYYY/MM/DD")
            variables["予約日時"] = f"{selected_date.month}月{selected_date.day}日"
        with col_b:
            selected_time = st.selectbox("予約時間", TIME_SLOTS, index=TIME_SLOTS.index("14:00"), key="booking_time")
            variables["予約時間"] = selected_time
        
        col_c, col_d = st.columns(2)
        with col_c:
            selected_method = st.selectbox("オンライン手段", list(ONLINE_METHODS.keys()), key="online_method")
            variables["オンライン手段"] = selected_method
        with col_d:
            auto_url = ONLINE_METHODS[selected_method]
            if auto_url:
                st.text_input("参加URL（自動反映）", value=auto_url, disabled=True, key="auto_url_display")
                variables["参加URL"] = auto_url
            else:
                st.info("📞 電話の場合、参加URLはありません")
                variables["参加URL"] = "（お電話にてご対応いたします）"
        
        if tid == "A-2":
            FIXED_PRE_INFO_URL = "https://managedtrust-service.studio.site/maikuru_purchase"
            st.text_input("事前情報入力URL（固定）", value=FIXED_PRE_INFO_URL, disabled=True, key="pre_info_url")
            variables["事前情報URL"] = FIXED_PRE_INFO_URL
        
        if tid == "A-3":
            image_url = st.text_input("画像アップロードURL", key="image_url", placeholder="https://...")
            variables["画像URL"] = image_url if image_url else "（画像URLを設定してください）"
    
    elif tid == "A-20":
        FIXED_IMAGE_URL = "https://managedtrust-service.studio.site/maikuru_purchase"
        st.text_input("画像アップロードURL（固定）", value=FIXED_IMAGE_URL, disabled=True, key="image_url_20")
        variables["画像URL"] = FIXED_IMAGE_URL
    
    elif tid == "A-4":
        st.caption("▼ 追客情報")
        BOOKING_URLS = {
            "自動車買取相談": "https://www.jicoo.com/t/EPUHG3-pVhTD/e/oeTySk2AEdTz",
            "自動車購入相談": "https://www.jicoo.com/t/EPUHG3-pVhTD/e/Re-vise"
        }
        col_bk1, col_bk2 = st.columns(2)
        with col_bk1:
            booking_type = st.selectbox("予約種別", list(BOOKING_URLS.keys()), key="booking_type")
        with col_bk2:
            auto_booking_url = BOOKING_URLS[booking_type]
            st.text_input("予約URL（自動反映）", value=auto_booking_url, disabled=True, key=f"auto_booking_url_{booking_type}")
        variables["予約URL"] = auto_booking_url
        st.text_area("前回商談のポイント（任意・メモ用）", key="memo", height=80, placeholder="メモとして記録されます")
    
    elif tid == "A-6":
        FIXED_FORM_URL = "https://managedtrust-service.studio.site/contract"
        st.text_input("フォームURL（固定）", value=FIXED_FORM_URL, disabled=True, key="form_url_display")
        variables["フォームURL"] = FIXED_FORM_URL
    
    elif tid == "A-10":
        base_date = st.date_input("基準日（この日以降で候補を聞く）", value=date.today(), key="base_date", format="YYYY/MM/DD")
        variables["基準日"] = f"{base_date.month}月{base_date.day}日"
    
    elif tid == "A-16":
        st.caption("▼ 陸送日程")
        col_e, col_f, col_g = st.columns(3)
        with col_e:
            delivery_date = st.date_input("引き上げ日", value=date.today(), key="delivery_date", format="YYYY/MM/DD")
        with col_f:
            delivery_time_from = st.selectbox("引き上げ開始時間", TIME_SLOTS, index=0, key="delivery_time_from")
        with col_g:
            from_idx = TIME_SLOTS.index(delivery_time_from)
            delivery_time_to = st.selectbox("引き上げ終了時間", TIME_SLOTS[from_idx:], index=0, key="delivery_time_to")
        if delivery_time_from == delivery_time_to:
            variables["確定日程"] = f"{delivery_date.month}月{delivery_date.day}日 {delivery_time_from}"
        else:
            variables["確定日程"] = f"{delivery_date.month}月{delivery_date.day}日 {delivery_time_from}〜{delivery_time_to}"
    
    elif tid == "A-23":
        amount = st.number_input("請求金額（円）", min_value=0, step=1000, key="amount")
        variables["請求金額"] = f"{amount:,}"
    
    elif tid == "A-18":
        payment_date = st.date_input("入金予定日", value=date.today(), key="payment_date", format="YYYY/MM/DD")
        variables["入金目安"] = f"{payment_date.month}月{payment_date.day}日"
    
    elif tid == "A-25":
        deposit_date = st.date_input("入金日", value=date.today(), key="deposit_date", format="YYYY/MM/DD")
        variables["入金日"] = f"{deposit_date.month}月{deposit_date.day}日"
    
    return variables, customer_name, email_to

# ===== Streamlit UI =====
st.set_page_config(page_title="顧客連絡AIエージェント", page_icon="📧", layout="wide")
st.title("📧 顧客連絡AIエージェント")
st.caption("ステップ1：トリガー選択 → ドラフト生成 → 許可ボタンで送信")

# 案件種別の選択（最上位レイヤー）
deal_type = st.sidebar.selectbox("案件種別", ["🚗 買取", "🏷️ 車販"], index=0, key="deal_type")
st.sidebar.markdown("---")

mode = st.sidebar.radio("モード選択", ["🔵 能動的連絡（こちらから送る）", "🟢 受動的連絡（返信を作成）", "⚙️ テンプレート管理"], index=0)

st.sidebar.markdown("---")
st.sidebar.markdown("### 送信ログ")
if os.path.exists("send_log.csv"):
    import pandas as pd
    log_df = pd.read_csv("send_log.csv", encoding="utf-8")
    st.sidebar.metric("総送信数", len(log_df))
    st.sidebar.dataframe(log_df.tail(5), use_container_width=True)
else:
    st.sidebar.info("まだ送信記録がありません")

if "🔵" in mode:
    # 案件種別に基づいてトリガーをフィルタリング
    current_deal_type = "買取" if "買取" in deal_type else "車販"
    
    phases = {}
    for t in TRIGGERS:
        if t["pattern"] == "受動":
            continue
        if t.get("deal_type", "買取") not in [current_deal_type, "共通"]:
            continue
        phase = t["phase"]
        if phase not in phases:
            phases[phase] = []
        phases[phase].append(t)
    
    if not phases:
        st.subheader(f"① トリガーを選択（{current_deal_type}）")
        st.info(f"🚧 {current_deal_type}用のトリガーは現在準備中です。\n\n「⚙️ テンプレート管理」の「➕ 新規追加」からテンプレートを追加し、triggers.jsonに車販用トリガーを登録してください。")
    else:
        st.subheader(f"① トリガーを選択（{current_deal_type}）")
        phase_names = list(phases.keys())
        tabs = st.tabs(phase_names)
        
        for tab, phase_name in zip(tabs, phase_names):
            with tab:
                cols = st.columns(3)
                for i, trigger in enumerate(phases[phase_name]):
                    with cols[i % 3]:
                        if st.button(f"#{trigger['id']} {trigger['name']}", key=f"trigger_{trigger['id']}", use_container_width=True):
                            st.session_state["selected_trigger_id"] = trigger["id"]
                            for key in ["draft_subject", "draft_body", "draft_trigger_name", "draft_customer_name", "draft_email_to"]:
                                if key in st.session_state:
                                    del st.session_state[key]
    
    if "selected_trigger_id" in st.session_state:
        trigger_id = st.session_state["selected_trigger_id"]
        trigger = next(t for t in TRIGGERS if t["id"] == trigger_id)
        
        st.markdown("---")
        st.subheader(f"② 情報入力：{trigger['name']}")
        status_badge = {"既存": "🔵", "新規": "🟡", "調整": "🟣"}
        st.caption(f"テンプレート：{trigger['template_id']} {status_badge.get(trigger['template_status'], '')} {trigger['template_status']}　|　{trigger['description']}")
        
        variables, customer_name, email_to = render_trigger_inputs(trigger)
        
        if st.button("📝 ドラフト生成", type="primary", use_container_width=True):
            if not customer_name:
                st.error("顧客名を入力してください")
            else:
                subject, body = fill_template(trigger["template_id"], variables)
                if subject and body:
                    st.session_state["draft_subject"] = subject
                    st.session_state["draft_body"] = body
                    st.session_state["draft_trigger_name"] = trigger["name"]
                    st.session_state["draft_customer_name"] = customer_name
                    st.session_state["draft_email_to"] = email_to
                else:
                    st.error(f"テンプレート {trigger['template_id']} が見つかりません")
        
        if "draft_subject" in st.session_state:
            st.markdown("---")
            st.subheader("③ ドラフト確認・修正")
            edited_subject = st.text_input("件名", value=st.session_state["draft_subject"], key="edit_subject")
            edited_body = st.text_area("本文", value=st.session_state["draft_body"], height=400, key="edit_body")
            edited_email_to = st.text_input("送信先メールアドレス", value=st.session_state.get("draft_email_to", ""), key="edit_email_to")
            
            col_send, col_reset = st.columns(2)
            with col_send:
                if st.button("✅ 許可（送信）", type="primary", use_container_width=True):
                    to_addr = edited_email_to
                    if not to_addr:
                        st.error("送信先メールアドレスを入力してください")
                    else:
                        with st.spinner("📨 メールを送信しています..."):
                            success, message = send_email(to_addr, edited_subject, edited_body)
                        if success:
                            save_log(st.session_state.get("draft_trigger_name", ""), st.session_state.get("draft_customer_name", ""), to_addr, edited_subject, "送信完了")
                            st.success(f"✅ メール送信完了！（送信先：{to_addr}）")
                            st.balloons()
                        else:
                            save_log(st.session_state.get("draft_trigger_name", ""), st.session_state.get("draft_customer_name", ""), to_addr, edited_subject, f"送信失敗：{message}")
                            st.error(f"❌ メール送信に失敗しました：{message}")
            with col_reset:
                if st.button("🔄 元に戻す", use_container_width=True):
                    for key in ["draft_subject", "draft_body", "draft_trigger_name", "draft_customer_name", "draft_email_to"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()

elif "🟢" in mode:
    st.subheader("① テンプレートを選んでメールを作成")
    
    customer_name_r = st.text_input("顧客名", key="r_customer_name", placeholder="例：山田太郎")
    email_to_r = st.text_input("送信先メールアドレス", key="r_email_to", placeholder="例：yamada@example.com")
    
    incoming_email = st.text_area("参考：顧客からの受信メール（任意）", height=150, placeholder="返信の参考にしたい場合、顧客からのメール本文をここに貼り付けてください...", key="incoming_email")
    
    st.markdown("---")
    st.subheader("② テンプレートを選択")
    
    template_labels = {
        "A-2": "A-2：商談予約確認",
        "A-3": "A-3：商談リマインド",
        "A-4": "A-4：再商談誘導（追客）",
        "A-6": "A-6：契約後フロー案内＋入力依頼",
        "A-10": "A-10：陸送候補日ヒアリング",
        "A-12": "A-12：書類催促",
        "A-16": "A-16：陸送日程確定",
        "A-18": "A-18：入金日確定報告",
        "A-20": "A-20：写真UL催促",
        "A-21": "A-21：ヒアリング未返信リマインド",
        "A-22": "A-22：フォロー連絡（追客）",
        "A-23": "A-23：残債不足分請求案内",
        "A-24": "A-24：支払催促",
        "A-25": "A-25：入金完了報告",
        "A-26": "A-26：マイくるプラス案内",
    }
    
    selected_template = st.selectbox(
        "使用するテンプレート",
        list(template_labels.keys()),
        format_func=lambda x: template_labels[x],
        key="r_template_select"
    )
    
    if st.button("📝 ドラフト生成", type="primary", use_container_width=True, key="r_generate"):
        if not customer_name_r:
            st.error("顧客名を入力してください")
        else:
            variables = {"顧客名": customer_name_r}
            subject, body = fill_template(selected_template, variables)
            
            if subject and body:
                st.markdown("---")
                st.subheader("③ ドラフト確認・修正")
                st.info(f"📋 テンプレート：{template_labels[selected_template]}")
                
                edited_subject_r = st.text_input("件名", value=subject, key="r_edit_subject")
                edited_body_r = st.text_area("本文", value=body, height=400, key="r_edit_body")
                
                col_send_r, col_reset_r = st.columns(2)
                with col_send_r:
                    if st.button("✅ 許可（送信）", type="primary", use_container_width=True, key="r_send"):
                        if not email_to_r:
                            st.error("送信先メールアドレスを入力してください")
                        else:
                            with st.spinner("📨 メールを送信しています..."):
                                success, message = send_email(email_to_r, edited_subject_r, edited_body_r)
                            if success:
                                save_log(f"手動：{selected_template}", customer_name_r, email_to_r, edited_subject_r, "送信完了")
                                st.success(f"✅ メール送信完了！（送信先：{email_to_r}）")
                                st.balloons()
                            else:
                                save_log(f"手動：{selected_template}", customer_name_r, email_to_r, edited_subject_r, f"送信失敗：{message}")
                                st.error(f"❌ メール送信に失敗しました：{message}")
                with col_reset_r:
                    if st.button("🔄 元に戻す", use_container_width=True, key="r_reset"):
                        st.rerun()

else:
    # ===== テンプレート管理画面 =====
    st.subheader("⚙️ テンプレート管理")
    st.caption("テンプレートの閲覧・編集・追加ができます。変更は即座に反映されます。")
    
    # テンプレートファイルを直接読み込み（キャッシュを使わない）
    def load_templates_fresh():
        with open("templates.json", "r", encoding="utf-8") as f:
            return json.load(f)
    
    def save_templates(templates_data):
        with open("templates.json", "w", encoding="utf-8") as f:
            json.dump(templates_data, f, ensure_ascii=False, indent=2)
    
    current_templates = load_templates_fresh()
    
    # テンプレート名をtemplates.jsonから取得（保存されていればそちらを優先）
    default_labels = {
        "A-2": "商談予約確認",
        "A-3": "商談リマインド",
        "A-4": "再商談誘導（追客）",
        "A-6": "契約後フロー案内＋入力依頼",
        "A-10": "陸送候補日ヒアリング",
        "A-12": "書類催促",
        "A-16": "陸送日程確定",
        "A-18": "入金日確定報告",
        "A-20": "写真UL催促",
        "A-21": "ヒアリング未返信リマインド",
        "A-22": "フォロー連絡（追客）",
        "A-23": "残債不足分請求案内",
        "A-24": "支払催促",
        "A-25": "入金完了報告",
        "A-26": "マイくるプラス案内",
    }
    template_labels_mgmt = {}
    for tid in current_templates:
        saved_name = current_templates[tid].get("name", "")
        if saved_name:
            template_labels_mgmt[tid] = f"{tid}：{saved_name}"
        else:
            template_labels_mgmt[tid] = f"{tid}：{default_labels.get(tid, tid)}"
    
    mgmt_tab1, mgmt_tab2, mgmt_tab3 = st.tabs(["📝 テンプレート編集", "➕ 新規追加", "📋 一覧表示"])
    
    with mgmt_tab1:
        st.markdown("### テンプレートを編集")
        
        edit_template_id = st.selectbox(
            "編集するテンプレート",
            list(current_templates.keys()),
            format_func=lambda x: template_labels_mgmt.get(x, x),
            key="edit_tmpl_select"
        )
        
        if edit_template_id and edit_template_id in current_templates:
            tmpl = current_templates[edit_template_id]
            
            st.markdown(f"**テンプレートID：{edit_template_id}**")
            
            new_name = st.text_input(
                "テンプレート名",
                value=tmpl.get("name", template_labels_mgmt.get(edit_template_id, edit_template_id).split("：", 1)[-1] if "：" in template_labels_mgmt.get(edit_template_id, "") else ""),
                key="edit_tmpl_name"
            )
            
            st.caption(f"差込変数：{', '.join(tmpl.get('variables', []))}")
            
            new_subject = st.text_input(
                "件名",
                value=tmpl["subject"],
                key="edit_tmpl_subject"
            )
            
            new_body = st.text_area(
                "本文",
                value=tmpl["body"],
                height=500,
                key="edit_tmpl_body"
            )
            
            col_save, col_preview = st.columns(2)
            
            with col_save:
                if st.button("💾 保存", type="primary", use_container_width=True, key="save_tmpl"):
                    current_templates[edit_template_id]["name"] = new_name
                    current_templates[edit_template_id]["subject"] = new_subject
                    current_templates[edit_template_id]["body"] = new_body
                    save_templates(current_templates)
                    st.cache_data.clear()
                    st.success(f"✅ {edit_template_id}：{new_name} を保存しました！")
            
            with col_preview:
                if st.button("👁️ プレビュー（テスト太郎様）", use_container_width=True, key="preview_tmpl"):
                    preview_body = new_body.replace("{{顧客名}}", "テスト太郎")
                    st.markdown("---")
                    st.markdown("**▼ プレビュー**")
                    st.text(f"件名：{new_subject.replace('{{顧客名}}', 'テスト太郎')}")
                    st.text_area("本文プレビュー", value=preview_body, height=400, disabled=True, key="preview_area")
    
    with mgmt_tab2:
        st.markdown("### 新しいテンプレートを追加")
        
        new_id = st.text_input("テンプレートID（例：A-27）", key="new_tmpl_id", placeholder="A-27")
        new_tmpl_name = st.text_input("テンプレート名", key="new_tmpl_name", placeholder="例：契約書署名完了のお礼")
        new_tmpl_subject = st.text_input("件名", key="new_tmpl_subject", placeholder="例：ご署名ありがとうございました")
        new_tmpl_vars = st.text_input("差込変数（カンマ区切り）", key="new_tmpl_vars", placeholder="例：顧客名, 署名日")
        new_tmpl_body = st.text_area(
            "本文（{{顧客名}}のように差込変数を使えます）",
            height=400,
            key="new_tmpl_body",
            placeholder="{{顧客名}}様\n\nお世話になっております。\nマイくるサポートセンターの古世でございます。\n\n..."
        )
        
        if st.button("➕ テンプレートを追加", type="primary", use_container_width=True, key="add_tmpl"):
            if not new_id:
                st.error("テンプレートIDを入力してください")
            elif new_id in current_templates:
                st.error(f"テンプレートID '{new_id}' は既に存在します。編集タブで変更してください。")
            elif not new_tmpl_body:
                st.error("本文を入力してください")
            else:
                current_templates[new_id] = {
                    "subject": new_tmpl_subject,
                    "variables": [v.strip() for v in new_tmpl_vars.split(",") if v.strip()],
                    "body": new_tmpl_body
                }
                save_templates(current_templates)
                st.cache_data.clear()
                st.success(f"✅ テンプレート '{new_id}：{new_tmpl_name}' を追加しました！")
    
    with mgmt_tab3:
        st.markdown("### テンプレート一覧")
        
        for tid, tmpl in current_templates.items():
            label = template_labels_mgmt.get(tid, tid)
            with st.expander(f"📄 {label}"):
                st.markdown(f"**件名：** {tmpl['subject']}")
                st.markdown(f"**差込変数：** {', '.join(tmpl.get('variables', []))}")
                st.text_area(
                    "本文",
                    value=tmpl["body"],
                    height=300,
                    disabled=True,
                    key=f"view_{tid}"
                )
