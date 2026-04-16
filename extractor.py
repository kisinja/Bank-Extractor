import streamlit as st
import pytesseract
from PIL import Image
import pandas as pd
import re
from pdf2image import convert_from_bytes
from pypdf import PdfReader

# Hide GitHub icon
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
**Upload images or PDFs → Get clean +254 phones, customer names & amounts**  
Name column is now cleaned (only actual customer name).
"""
)

uploaded_files = st.file_uploader(
    "Upload Equity Bank statement(s)",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True,
)


def normalize_phone(phone_raw: str) -> str:
    phone = re.sub(r"\D", "", phone_raw.strip())
    if len(phone) == 12 and phone.startswith("254"):
        return f"+{phone}"
    elif len(phone) == 10 and phone.startswith("07"):
        return f"+254{phone[1:]}"
    elif len(phone) == 9 and phone.startswith("7"):
        return f"+254{phone}"
    return phone


def clean_name(name_raw: str) -> str:
    """Clean the name: remove amounts, dates, HEAD OFFICE, PO Box, etc."""
    name = name_raw.strip()

    # Remove common unwanted patterns at the end of name
    name = re.sub(
        r"\d{1,3}(?:,\d{3})*(?:\.\d{2})?", "", name
    )  # remove amounts like 2,800.00
    name = re.sub(r"\d{2}-\d{2}-\d{4}", "", name)  # remove dates like 24-04-2024
    name = re.sub(r"HEAD OFFICE.*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"PO\.?\s*Box.*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"APP/.*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"EAZZ.*", "", name, flags=re.IGNORECASE)

    # Remove extra spaces and trailing numbers/words
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\s+\d+$", "", name)  # remove trailing numbers

    return name if name else "Unknown"


def extract_transactions(raw_text: str):
    cleaned = re.sub(r"\s+", " ", raw_text).strip()

    # Improved pattern: captures phone, then code, then 0733457904, then name (stops before next MPS or junk)
    pattern = r"MPS\s+(\d{12})\s+\S+\s+0733457904\s+([A-Za-z\s]+?)(?=\s+MPS\s+\d{12}|\s+\d{1,3}(?:,\d{3})*(?:\.\d{2})|\s+HEAD OFFICE|\Z)"

    transactions = re.findall(pattern, cleaned, re.IGNORECASE)

    # Extract Credit amounts (every even monetary value)
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
    for i, (phone_raw, name_raw) in enumerate(transactions):
        clean_name_str = clean_name(name_raw)
        if i < len(credits):
            extracted.append(
                {"raw_phone": phone_raw, "name": clean_name_str, "amount": credits[i]}
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

        data = [
            {
                "Phone": phone,
                "Name": info["name"],
                "Amount (KSh)": round(info["total"], 2),
            }
            for phone, info in customer_dict.items()
        ]
        df = pd.DataFrame(data)
        df["Phone"] = df["Phone"].astype(str)

        st.success(f"✅ Extracted **{len(df)} unique customers** with clean names!")
        st.dataframe(df, use_container_width=True, hide_index=True)

        csv = df.to_csv(index=False, quoting=1)
        st.download_button(
            label="📥 Download customers.csv",
            data=csv,
            file_name="customers.csv",
            mime="text/csv",
            type="primary",
        )

        st.caption(
            "✅ Clean customer names only • Phones in +254 format • Amounts summed"
        )
    else:
        st.warning("⚠️ No transactions extracted. Try clearer docs.")
else:
    st.info("👆 Upload your Equity Bank statement image(s) or PDF(s)")

st.markdown("---")
st.caption("Name column cleaned | GitHub icon hidden")
