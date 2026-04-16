import streamlit as st
import pytesseract
from PIL import Image
import pandas as pd
import re
from pdf2image import convert_from_bytes
from pypdf import PdfReader
from datetime import datetime

# Hide GitHub icon
st.markdown("""
<style>
header { visibility: hidden; }
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

st.set_page_config(
    page_title="Equity Extractor",
    page_icon="🏦",
    layout="centered"
)

st.title("🏦 Equity Bank Statement Customer Extractor")
st.markdown("""
**Upload images or PDFs → Get clean +254 phones, customer names, amounts & Top Customers Ranking**
""")

uploaded_files = st.file_uploader(
    "Upload Equity Bank statement(s)",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True
)

def normalize_phone(phone_raw: str) -> str:
    phone = re.sub(r'\D', '', phone_raw.strip())
    if len(phone) == 12 and phone.startswith("254"):
        return f"+{phone}"
    elif len(phone) == 10 and phone.startswith("07"):
        return f"+254{phone[1:]}"
    elif len(phone) == 9 and phone.startswith("7"):
        return f"+254{phone}"
    return phone

def clean_name(name_raw: str) -> str:
    name = name_raw.strip()
    name = re.sub(r'\d{1,3}(?:,\d{3})*(?:\.\d{2})?', '', name)      # remove amounts
    name = re.sub(r'\d{2}-\d{2}-\d{4}', '', name)                   # remove dates
    name = re.sub(r'HEAD OFFICE.*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'PO\.?\s*Box.*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'APP/.*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'EAZZ.*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'\s+\d+$', '', name)
    return name if name else "Unknown"

def extract_transactions(raw_text: str):
    cleaned = re.sub(r'\s+', ' ', raw_text).strip()
    pattern = r'MPS\s+(\d{12})\s+\S+\s+0733457904\s+([A-Za-z\s]+?)(?=\s+MPS\s+\d{12}|\s+\d{1,3}(?:,\d{3})*(?:\.\d{2})|\s+HEAD OFFICE|\Z)'
    
    transactions = re.findall(pattern, cleaned, re.IGNORECASE)
    
    money_pattern = r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)'
    all_amounts = re.findall(money_pattern, cleaned)
    credits = []
    for i in range(len(all_amounts)):
        if i % 2 == 0:
            try:
                credits.append(float(all_amounts[i].replace(',', '')))
            except:
                pass
    
    extracted = []
    for i, (phone_raw, name_raw) in enumerate(transactions):
        clean_name_str = clean_name(name_raw)
        if i < len(credits):
            extracted.append({
                "raw_phone": phone_raw,
                "name": clean_name_str,
                "amount": credits[i]
            })
    return extracted

if uploaded_files:
    all_transactions = []
    
    with st.spinner("🔍 Processing statements..."):
        for file in uploaded_files:
            try:
                if file.type == "application/pdf":
                    pdf_reader = PdfReader(file)
                    native_text = ""
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            native_text += page_text + "\n"
                    
                    if native_text.strip():
                        all_transactions.extend(extract_transactions(native_text))
                    else:
                        file.seek(0)
                        images = convert_from_bytes(file.read(), dpi=300)
                        for img in images:
                            text = pytesseract.image_to_string(img, lang='eng')
                            all_transactions.extend(extract_transactions(text))
                else:
                    image = Image.open(file)
                    text = pytesseract.image_to_string(image, lang='eng')
                    all_transactions.extend(extract_transactions(text))
            except Exception as e:
                st.error(f"Error processing {file.name}: {str(e)}")
    
    if all_transactions:
        # Deduplicate and sum amounts
        customer_dict = {}
        for tx in all_transactions:
            phone = normalize_phone(tx["raw_phone"])
            name = tx["name"]
            amount = tx["amount"]
            
            if phone not in customer_dict:
                customer_dict[phone] = {"name": name, "total": amount}
            else:
                customer_dict[phone]["total"] += amount
                if len(name) > len(customer_dict[phone]["name"]):
                    customer_dict[phone]["name"] = name
        
        # Build DataFrame with Rank
        data = [
            {
                "Rank": 0,  # Will be filled later
                "Phone": phone,
                "Name": info["name"],
                "Amount (KSh)": round(info["total"], 2)
            }
            for phone, info in customer_dict.items()
        ]
        df = pd.DataFrame(data)
        df["Phone"] = df["Phone"].astype(str)
        
        # Add Ranking (sorted by Amount descending)
        df = df.sort_values(by="Amount (KSh)", ascending=False).reset_index(drop=True)
        df["Rank"] = df.index + 1
        
        # Reorder columns
        df = df[["Rank", "Phone", "Name", "Amount (KSh)"]]
        
        # ====================== TOP CUSTOMERS SECTION ======================
        st.subheader("🏆 Top Customers Ranking")
        top_n = 10
        top_customers = df.head(top_n).copy()
        
        # Add medal emojis for top 3
        def add_medal(rank):
            if rank == 1: return "🥇"
            elif rank == 2: return "🥈"
            elif rank == 3: return "🥉"
            else: return f"{rank}."
        
        top_customers["Customer"] = top_customers.apply(
            lambda row: f"{add_medal(row['Rank'])} {row['Name']}", axis=1
        )
        
        ranking_display = top_customers[["Customer", "Amount (KSh)"]].reset_index(drop=True)
        st.dataframe(ranking_display, use_container_width=True, hide_index=True)
        
        st.success(f"✅ Extracted **{len(df)} unique customers** • Top {top_n} shown above")
        
        # Main full table
        st.subheader("📋 All Customers")
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Dynamic filename with today's date
        today = datetime.now().strftime("%Y-%m-%d")
        download_filename = f"customers-{today}.csv"
        
        csv = df.to_csv(index=False, quoting=1)
        
        st.download_button(
            label=f"📥 Download {download_filename}",
            data=csv,
            file_name=download_filename,
            mime="text/csv",
            type="primary",
        )
        
        st.caption("✅ Clean names • Ranked by amount • Phones in +254 format")
        
    else:
        st.warning("⚠️ No transactions could be extracted. Try clearer images.")
else:
    st.info("👆 Upload your Equity Bank statement image(s) or PDF(s) to begin.")

st.markdown("---")