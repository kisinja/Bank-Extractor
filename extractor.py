import streamlit as st
import pytesseract
from PIL import Image
import pandas as pd
import re
from pdf2image import convert_from_bytes
from pypdf import PdfReader

# Hide github icon
st.markdown(
    """
<style>
header { visibility: hidden; }
footer { visibility: hidden; }
</style>
""",
    unsafe_allow_html=True,
)

st.set_page_config(page_title="Equity Extractor", page_icon="🏦", layout="centered")

st.title("🏦 Equity Bank Statement Customer Extractor")
st.markdown(
    """
**Upload images or PDFs → Get +254 phones, names & amounts (deduplicated)**  
Supports both text-based PDFs and scanned PDFs.
"""
)

uploaded_files = st.file_uploader(
    "Upload Equity Bank statement(s)",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True,
    help="You can upload multiple files",
)


def normalize_phone(phone_raw: str) -> str:
    """Convert Kenyan numbers to +254 format"""
    phone = re.sub(r"\D", "", phone_raw.strip())
    if len(phone) == 12 and phone.startswith("254"):
        return f"+{phone}"
    elif len(phone) == 10 and phone.startswith("07"):
        return f"+254{phone[1:]}"
    elif len(phone) == 9 and phone.startswith("7"):
        return f"+254{phone}"
    return phone


def extract_transactions(raw_text: str):
    cleaned = re.sub(r"\s+", " ", raw_text).strip()
    pattern = r"MPS\s+(\d{12})\s+\S+\s+0733457904\s+(.+?)(?=\s+MPS\s+\d{12}|\Z)"
    transactions = re.findall(pattern, cleaned, re.IGNORECASE)

    money_pattern = r"(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)"
    all_amounts = re.findall(money_pattern, cleaned)
    credits = []
    for i in range(len(all_amounts)):
        if i % 2 == 0:
            try:
                credits.append(float(all_amounts[i].replace(",", "")))
            except:
                pass

    extracted = []
    for i, (phone_raw, name) in enumerate(transactions):
        name = name.strip() or "Unknown"
        if i < len(credits):
            extracted.append(
                {"raw_phone": phone_raw, "name": name, "amount": credits[i]}
            )
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
                            text = pytesseract.image_to_string(img, lang="eng")
                            all_transactions.extend(extract_transactions(text))
                else:
                    image = Image.open(file)
                    text = pytesseract.image_to_string(image, lang="eng")
                    all_transactions.extend(extract_transactions(text))
            except Exception as e:
                st.error(f"Error processing {file.name}: {str(e)}")

    if all_transactions:
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

        # Build DataFrame with Phone as string to prevent scientific notation
        data = [
            {
                "Phone": phone,  # Kept as string
                "Name": info["name"],
                "Amount (KSh)": round(info["total"], 2),
            }
            for phone, info in customer_dict.items()
        ]
        df = pd.DataFrame(data)

        # Force Phone column to be text (important for CSV)
        df["Phone"] = df["Phone"].astype(str)

        st.success(f"✅ Successfully extracted **{len(df)} unique customers**!")
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Improved CSV download - forces text format for Phone
        csv = df.to_csv(index=False, quoting=1)  # quoting=1 helps with strings

        st.download_button(
            label="📥 Download customers.csv (Phone numbers fixed)",
            data=csv,
            file_name="customers.csv",
            mime="text/csv",
            type="primary",
        )

        st.caption(
            "✅ Phones in +254 format (saved as text) • Duplicates removed • Amounts summed"
        )
        st.info(
            "💡 Tip: When opening in Excel, the Phone column should now show full numbers. If not, select the column → Format Cells → Text."
        )
    else:
        st.warning("⚠️ No transactions could be extracted.")
else:
    st.info("👆 Upload your Equity Bank statement image(s) or PDF(s)")

st.markdown("---")
st.caption("Hosted version | Phone numbers fixed for Excel")
