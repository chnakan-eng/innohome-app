import streamlit as st
import pandas as pd
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import urllib.parse
import re
import os

# --- 🚀 สั่งให้ Cloud ติดตั้งเบราว์เซอร์ ---
@st.cache_resource
def install_playwright():
    os.system("playwright install chromium")
install_playwright()

# --- 🔐 1. ข้อมูลล็อคอินภายในองค์กร (Internal Only) ---
INTERNAL_USERS = {
    "innohome01": "innohome01-"
}

# --- 🎨 2. CUSTOM CSS ---
def local_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;500;600&family=Poppins:wght@400;600&display=swap');
        html, body, [class*="css"] { font-family: 'Kanit', 'Poppins', sans-serif; }
        .block-container { max-width: 1400px !important; }
        .stat-card { background-color: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.04); border-left: 5px solid #ddd; }
        .header-container { text-align: center; border-bottom: 1px solid #e2e8f0; margin-bottom: 2rem; padding: 1rem; }
        .login-box { max-width: 400px; margin: 50px auto; padding: 30px; background: white; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); }
        .login-title { text-align: center; color: #0f172a; font-weight: 600; font-size: 2rem; margin-bottom: 10px; }
        .login-subtitle { text-align: center; color: #64748b; font-size: 0.9rem; margin-bottom: 25px; }
        </style>
    """, unsafe_allow_html=True)

def clean_and_calculate(price_str, size_str):
    try:
        price_digits = re.sub(r'[^\d]', '', price_str)
        if not price_digits: return 0, 0, 0
        price_val = float(price_digits)
        size_match = re.search(r'(\d+(?:\.\d+)?)', size_str)
        if not size_match: return 0, 0, 0
        size_val = float(size_match.group(1))
        if size_val == 0: return 0, 0, 0
        price_per_sqm = price_val / size_val
        return size_val, price_val, price_per_sqm
    except:
        return 0, 0, 0

async def scrape_ddproperty(page, condo_name, max_pages):
    data_list = []
    query_encoded = urllib.parse.quote_plus(condo_name)
    for current_page in range(1, max_pages + 1):
        url = f"https://www.ddproperty.com/en/property-for-sale/{current_page if current_page > 1 else ''}?freetext={query_encoded}"
        try:
            await page.goto(url, timeout=60000)
            await page.wait_for_timeout(4000) 
            for _ in range(3): await page.mouse.wheel(0, 1000); await page.wait_for_timeout(800)
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            listings = soup.find_all("div", attrs={"data-automation-id": "listing-card"}) or soup.find_all("div", class_=lambda x: x and 'listing-card' in str(x).lower())
            for room in listings:
                full_text = room.get_text(separator=" ").strip()
                full_text = re.sub(r'\s+', ' ', full_text)
                title_elem = room.find("a", class_="nav-link") or room.find("h3")
                title = title_elem.text.strip() if title_elem else condo_name
                if "Profile" in title: continue
                price_elem = room.find("span", class_="price") or room.find(string=lambda t: t and '฿' in t)
                if not price_elem: continue
                price_str = price_elem.get_text().strip() if hasattr(price_elem, 'get_text') else str(price_elem).strip()
                size_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:sqm|sq\.m\.|ตร\.ม\.)', full_text, re.IGNORECASE)
                size_str = f"{size_match.group(1)} Sqm" if size_match else "0 Sqm"
                size_num, price_num, p_sqm = clean_and_calculate(price_str, size_str)
                if price_num < 500000 or p_sqm == 0: continue 
                link = "https://www.ddproperty.com" + room.find("a")["href"] if room.find("a") else "#"
                data_list.append({
                    "แพลตฟอร์ม": "DDproperty 🔴", "หัวข้อประกาศ": title, "Location": condo_name,
                    "ขนาด_num": size_num, "ขนาด": f"{size_num:,.2f} Sqm", "ราคาประกาศขาย": f"฿{price_num:,.0f}",
                    "ราคา_num": price_num, "ราคาต่อตารางเมตร": p_sqm, "ลิงก์": link
                })
        except: pass
    return data_list

async def scrape_livinginsider(page, condo_name, max_pages):
    data_list = []
    try:
        await page.goto("https://www.livinginsider.com/", timeout=60000)
        await page.wait_for_timeout(3000)
        search_box = page.locator('input[placeholder*="โครงการ"]:visible, input[placeholder*="ทำเล"]:visible').first
        await search_box.fill(condo_name)
        await page.wait_for_timeout(3500)
        await page.keyboard.press("ArrowDown"); await page.wait_for_timeout(500); await page.keyboard.press("Enter")
        await page.wait_for_timeout(5000)
        for current_page in range(1, max_pages + 1):
            if current_page > 1:
                next_p = page.locator(f'ul.pagination a, div.pagination a').filter(has_text=str(current_page)).first
                if await next_p.count() > 0: await next_p.click(); await page.wait_for_timeout(4000)
                else: break
            for _ in range(4): await page.mouse.wheel(0, 800); await page.wait_for_timeout(600)
            html = await page.content(); soup = BeautifulSoup(html, "html.parser")
            listings = soup.find_all("div", class_=lambda c: c and ('istock-list' in c or 'item-desc' in c or 'box-property' in c))
            for room in listings:
                text = room.get_text(separator=" ").strip()
                price_match = re.search(r'([1-9][0-9]{0,2}(?:,[0-9]{3})+)', text)
                if not price_match: continue
                price_str = price_match.group(1)
                size_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:ตร\.ม\.|ตรม|sq\.m|sqm)', text, re.IGNORECASE)
                size_str = f"{size_match.group(1)} Sqm" if size_match else "0 Sqm"
                size_num, price_num, p_sqm = clean_and_calculate(price_str, size_str)
                if price_num < 500000 or p_sqm == 0: continue
                title_elem = room.find("a")
                title = title_elem.text.strip() if title_elem else condo_name
                loc_elem = room.find("div", class_=lambda c: c and 'zone-text' in c) or room.find("span", class_=lambda c: c and 'txt-dark-grey' in c)
                location = loc_elem.text.strip() if loc_elem else condo_name
                link_elem = room.find("a", href=True)
                link = link_elem["href"] if link_elem else page.url
                if not link.startswith("http"): link = "https://www.livinginsider.com" + link
                data_list.append({
                    "แพลตฟอร์ม": "Livinginsider 🔵", "หัวข้อประกาศ": title, "Location": location,
                    "ขนาด_num": size_num, "ขนาด": f"{size_num:,.2f} Sqm", "ราคาประกาศขาย": f"฿{price_num:,.0f}",
                    "ราคา_num": price_num, "ราคาต่อตารางเมตร": p_sqm, "ลิงก์": link
                })
    except: pass
    return data_list

async def run_dual_engine(condo_name, max_pages):
    combined = []
    seen = set()
    async with async_playwright() as p:
        # 🔥 ระบบพรางตัว (ตั้งค่าให้เหมือนคนเล่นเน็ตปกติ)
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--disable-blink-features=AutomationControlled", 
                "--no-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-web-security"
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='th-TH',
            timezone_id='Asia/Bangkok'
        )
        p_dd = await context.new_page(); p_lv = await context.new_page()
        res_dd, res_lv = await asyncio.gather(scrape_ddproperty(p_dd, condo_name, max_pages), scrape_livinginsider(p_lv, condo_name, max_pages))
        await browser.close()
        for item in (res_dd + res_lv):
            key = (item["ขนาด"], item["ราคาประกาศขาย"])
            if key not in seen: combined.append(item); seen.add(key)
    return combined

# --- 🏗️ 4. UI STRUCTURE & LOGIN SYSTEM ---
st.set_page_config(page_title="Innohome - Internal System", layout="wide")
local_css()

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ""

if not st.session_state['logged_in']:
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">Innohome Pro</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-subtitle">ระบบประเมินราคาอสังหาริมทรัพย์ (Internal Use Only)</div>', unsafe_allow_html=True)
    
    input_user = st.text_input("Username (ID)", placeholder="กรอกรหัสพนักงาน")
    input_pass = st.text_input("Password", placeholder="กรอกรหัสผ่าน", type="password")
    
    if st.button("เข้าสู่ระบบ", use_container_width=True, type="primary"):
        if input_user in INTERNAL_USERS and INTERNAL_USERS[input_user] == input_pass:
            st.session_state['logged_in'] = True
            st.session_state['username'] = input_user
            st.rerun()
        else:
            st.error("❌ Username หรือ Password ไม่ถูกต้องครับ!")
    st.markdown('</div>', unsafe_allow_html=True)

else:
    col_logo, col_logout = st.columns([8, 1])
    with col_logout:
        if st.button("🚪 Logout"):
            st.session_state['logged_in'] = False
            st.session_state['username'] = ""
            st.rerun()

    st.markdown(f'<div class="header-container"><h1>Innohome <span style="color:#ef4444;">V7</span> (Internal Edition)</h1><p>ยินดีต้อนรับทีมงาน (ID: <b>{st.session_state["username"]}</b>)</p></div>', unsafe_allow_html=True)

    col_in, col_p, col_b = st.columns([4, 1, 1])
    condo_name = col_in.text_input("ชื่อโครงการคอนโด", placeholder="เช่น the room 64...", label_visibility="collapsed")
    max_p = col_p.number_input("หน้าเว็บ", 1, 5, 1, label_visibility="collapsed")
    start_btn = col_b.button("ค้นหา")

    if start_btn and condo_name:
        with st.spinner("🤖 บอทกำลังดึงข้อมูลจาก DDproperty และ Livinginsider (รอประมาณ 1-2 นาที)..."):
            results = asyncio.run(run_dual_engine(condo_name, max_p))
            if results:
                df = pd.DataFrame(results)
                p_sqm_list = df["ราคาต่อตารางเมตร"].tolist()
                max_v, min_v, avg_v = max(p_sqm_list), min(p_sqm_list), sum(p_sqm_list)/len(p_sqm_list)
                
                df["มูลค่าสูงสุดตลาด"] = df["ขนาด_num"] * max_v
                df["มูลค่าต่ำสุดตลาด"] = df["ขนาด_num"] * min_v
                df["มูลค่าเฉลี่ยตลาด"] = df["ขนาด_num"] * avg_v
                
                df["ราคาต่อตารางเมตร_display"] = df["ราคาต่อตารางเมตร"].map("฿{:,.0f} / Sqm".format)
                df["มูลค่าสูงสุดตลาด"] = df["มูลค่าสูงสุดตลาด"].map("฿{:,.0f}".format)
                df["มูลค่าต่ำสุดตลาด"] = df["มูลค่าต่ำสุดตลาด"].map("฿{:,.0f}".format)
                df["มูลค่าเฉลี่ยตลาด"] = df["มูลค่าเฉลี่ยตลาด"].map("฿{:,.0f}".format)
                
                c1, c2, c3 = st.columns(3)
                c1.markdown(f'<div class="stat-card" style="border-left-color:#dc2626;"><div style="color:#dc2626; font-size:0.95rem; font-weight:600; margin-bottom:5px;">🔺 ราคาสูงสุด/ตร.ม.</div><div style="color:#dc2626; font-size: 1.8rem; font-weight: 700;">฿{max_v:,.0f}</div></div>', unsafe_allow_html=True)
                c2.markdown(f'<div class="stat-card" style="border-left-color:#16a34a;"><div style="color:#16a34a; font-size:0.95rem; font-weight:600; margin-bottom:5px;">🟢 ราคาต่ำสุด/ตร.ม.</div><div style="color:#16a34a; font-size: 1.8rem; font-weight: 700;">฿{min_v:,.0f}</div></div>', unsafe_allow_html=True)
                c3.markdown(f'<div class="stat-card" style="border-left-color:#d97706;"><div style="color:#d97706; font-size:0.95rem; font-weight:600; margin-bottom:5px;">🟡 ราคาเฉลี่ย/ตร.ม.</div><div style="color:#d97706; font-size: 1.8rem; font-weight: 700;">฿{avg_v:,.0f}</div></div>', unsafe_allow_html=True)
                
                st.write("")
                cols = ["แพลตฟอร์ม", "หัวข้อประกาศ", "Location", "ขนาด", "ราคาประกาศขาย", "มูลค่าสูงสุดตลาด", "มูลค่าต่ำสุดตลาด", "มูลค่าเฉลี่ยตลาด", "ราคาต่อตารางเมตร_display", "ลิงก์"]
                
                def highlight(row):
                    if row["ราคาต่อตารางเมตร"] == max_v: 
                        return ['background-color: #fee2e2; color: #991b1b; font-weight: 600;'] * len(row)
                    if row["ราคาต่อตารางเมตร"] == min_v: 
                        return ['background-color: #dcfce7; color: #166534; font-weight: 600;'] * len(row)
                    return [''] * len(row)

                st.dataframe(df.style.apply(highlight, axis=1), width=1600, hide_index=True, column_order=cols)
                csv = df[cols].to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 ดาวน์โหลดรายงาน Appraisal Report", csv, f"{condo_name}_appraisal.csv", "text/csv")
            else:
                st.warning("ไม่พบข้อมูลประกาศขายในขณะนี้")
