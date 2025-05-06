import streamlit as st
import pandas as pd
import os
from simple_salesforce import Salesforce
from google.cloud import secretmanager
import json
from time import sleep, strftime
from io import BytesIO

# Define a temporary folder for storing uploaded and generated files
TEMP_FOLDER = "temp"
os.makedirs(TEMP_FOLDER, exist_ok=True)
timestr = strftime("%Y%m%d_%H%M%S_")

# Streamlit UI
st.title("Salesforce Acquisition Duplicate Processing Tool")

# Key uploader
Key_file = st.file_uploader("📂 Upload Key File", type=["json"])

# Set the path dynamically only after the file is uploaded
if Key_file:
    Key_path = os.path.join(TEMP_FOLDER, Key_file.name)
    with open(Key_path, "wb") as f:
        f.write(Key_file.getbuffer())

    # Now that the file exists, set the environment variable
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = Key_path
    st.success(f"✅ Key file saved and environment variable set!")

# File uploaders
Service_file = st.file_uploader("📂 Upload Service Code File", type=["xlsx"])


# Save uploaded files into the temp folder
Service_path = None
salesforce_path = None
sf_conn = None

if Service_file:
    Service_path = os.path.join(TEMP_FOLDER, Service_file.name)
    with open(Service_path, "wb") as f:
        f.write(Service_file.getbuffer())
    st.success(f"✅ Service code file saved")

# Title
st.title("🔐 Salesforce Login + Add to Prod")

# 1) LOGIN SECTION
SF_UserName = st.text_input(
    "🔄 Salesforce User Name",
    key="sf_username"        # <-- unique key
)
SF_Password = st.text_input(
    "🔄 Salesforce Password",
    type="password",
    key="sf_password"        # <-- unique key
)
login_clicked = st.button(
    "🔐 Login",
    key="login_button"       # <-- also give your buttons keys if you get duplicates
)

if login_clicked:
    global sf_conn
    try:
        secrets = get_secret("Salesforce_Key", "selesforce-455620")
        env_data = secrets.get(environment, {})
        URL = env_data.get("url")
        KEY = env_data.get("key")
        SECRET = env_data.get("secret")
        if not (URL and KEY and SECRET):
            st.error(f"⚠️ Missing credentials for {environment}")
        else:
            sf_conn = Salesforce(
            username=SF_UserName,
            password=SF_Password,
            instance_url=URL,
            consumer_key=KEY,
            consumer_secret=SECRET,
        )
        st.session_state["sf"] = sf_conn
        st.success("✅ Logged in to Salesforce")
    except Exception as e:
        sf_conn = None
        st.error(f"❌ Authentication failed: {e}")

# 2) ADD TO PROD SECTION
# Only show “Add to Prod” once we've stored st.session_state.sf
if "sf" in st.session_state:
    st.write("You are logged in.  Ready to push to Production:")
    add_clicked = st.button("✅ Add to Prod")
    if add_clicked:
        if Service_path is None:
            st.error("Please upload the service file first.")
        else:
            # Read the Excel file into df
            df = pd.read_excel(Service_path)
            try:
                Create_Service_Code(df)
                st.success("🎉 Service code pushed to Production!")
            except Exception as e:
                st.error(f"Error during production push: {e}")


# Your allowed sets
allowed_sets = {
    "Unit_of_Measurement__c": [
        "Each",
        "Flat",
        "Bin",
        "Bulk",
        "Case",
        "Combo",
        "Container",
        "Dolly",
        "Drum",
        "LBs - Gross",
        "LBs - Net",
        "Hour",
        "Hundred Weight Lbs - Gross",
        "Hundred Weight Lbs - Net",
        "Kilogram - Gross",
        "Kilogram - Net",
        "Hundred Kilogram - Gross",
        "Hundred Kilogram - Net",
        "Kilowatt Hour",
        "Load",
        "Lot",
        "Pallet",
        "Railcar",
        "Square Foot",
        "Square Meter",
        "Tote",
        "Truck",
        "Trailer",
        "Tub",
        "CWT",
        "Metric Ton"
    ],
    "lcpq_Invoice_Type_Code__c": ["WR", "AN", "RN"],
    "lcpq_Rebill_Passthrough_Service__c": ["No", "Cost", "Cost + Markup"],
    "lcpq_Standard_vs_Non_Standard_UOM__c": ["Standard", "Non-Standard"],
    "lcpq_Service_Code_Categorization__c": [
        "API Name",
        "Standard",
        "Standard, Approval Required",
        "Legacy",
    ],
    "Charge_Break_Flag__c": ["F", "B", "C"],
    "Charge_Type_Code__c": [
        "CIO",
        "DAVM",
        "DAVS",
        "DENS",
        "MAXD",
        "MAXX",
        "MULT",
        "MXCX",
        "NC",
        "SING",
    ],
    "lcpq_Catalog_Category__c": [
        "Storage & Handling",
        "Accessorials",
        "Storage & Handling for Density",
        "Boxing Services",
        "Revenue Override",
        "Storage & Handling for PNW",
        "Storage & Handling for Vernon",
    ],
    "lcpq_DG_Boxing_Defrost_Language__c": [True, False],
    "lcpq_Exclude_from_Documents__c": [True, False],
    "lcpq_Rollup_Category__c": [
        "Storage",
        "Handling",
        "Accessorial",
        "Blast Freeze",
        "Case Pick",
        "Floor Loading",
        "Floor Unloading",
        "Shrink Wrap",
    ],
    "lcpq_Subcategory__c": [
        "Accessorial",
        "Blast Freeze",
        "Case Pick",
        "Handling",
        "Storage",
    ],
    "SBQQ__SubscriptionPricing__c": ["Fixed Price"],
}

def check_service_file(file, output_path):
    error_flag = False
    df = pd.read_excel(file)
    for column, allowed_values in allowed_sets.items():
        if column in df.columns:
            invalid_values = set(df[column].unique()) - set(allowed_values)
            if invalid_values:
                if "Data Issue" not in df.columns:
                    df["Data Issue"] = ""
                df.loc[df[column].isin(invalid_values), "Data Issue"] = (
                    f"Invalid values in {column}"
                )
                error_flag = True
        else:
            st.warning(f"Column '{column}' not found in uploaded file.")
            error_flag = True

    if error_flag:
        error_file_path = os.path.join(output_path, f"{timestr}Data_Errors_ServiceCodeTemplate.xlsx")
        df.to_excel(error_file_path, index=False)
        return error_file_path  # Return path to download
    return None

if Service_file:
    Service_path = os.path.join(TEMP_FOLDER, Service_file.name)
    with open(Service_path, "wb") as f:
        f.write(Service_file.getbuffer())
    st.success(f"✅ Service code file saved")

    if st.button("✅ Check File for Valid Values"):
        result = check_service_file(Service_path, TEMP_FOLDER)
        if result:
            st.error("❌ Issues found in the uploaded file. Please download and review.")
            with open(result, "rb") as f:
                st.download_button(
                    label="📥 Download Error File",
                    data=f,
                    file_name=os.path.basename(result),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.success("🎉 No issues found! File is valid.")


# Function to retrieve secrets
def get_secret(secret_id, project_id="selesforce-455620"):
    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"

    response = client.access_secret_version(request={"name": secret_name})
    secret_data = response.payload.data.decode("UTF-8")

    return json.loads(secret_data)  # Convert JSON string to Python dictionary

# Salesforce environment
environment = "PROD"
# Convert DataFrame to Excel in memory
def to_excel_buffer(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    output.seek(0)
    return output

     
def Create_Service_Code(x):
    Column_header = [
        "Name",
        "ProductCode",
        "Unit_of_Measurement__c",
        "Description",
        "lcpq_Invoice_Type_Code__c",
        "lcpq_Rebill_Passthrough_Service__c",
        "lcpq_Standard_vs_Non_Standard_UOM__c",
        "lcpq_Service_Code_Categorization__c",
        "Charge_Break_Flag__c",
        "Charge_Type_Code__c",
        "lcpq_Document_Service_Description__c",
        "lcpq_Catalog_Category__c",
        "SBQQ__Component__c",
        "SBQQ__DefaultQuantity__c",
        "SBQQ__Optional__c",
        "SBQQ__QuantityEditable__c",
        "SBQQ__SubscriptionPricing__c",
        "SBQQ__SubscriptionType__c",
        "lcpq_CPQ_Service__c",
        "lcpq_DG_Boxing_Defrost_Language__c",
        "lcpq_Exclude_from_Documents__c",
        "Family",
        "IsActive",
        "lcpq_Rollup_Category__c",
        "lcpq_Subcategory__c",
        "SBQQ__ConfigurationType__c",
        "lcpq_Per_Order_Min_Flag__c",
        "SBQQ__ConfigurationEvent__c",
        "SBQQ__HidePriceInSearchResults__c",
        "SBQQ__ExcludeFromOpportunity__c",
    ]
    feature = pd.DataFrame(columns=Column_header)
    for i, item in enumerate(x["Name"]):
        feature.loc[len(feature.index)] = [
            x["Name"][i],
            x["ProductCode"][i],
            x["Unit_of_Measurement__c"][i],
            x["Description"][i],
            x["lcpq_Invoice_Type_Code__c"][i],
            x["lcpq_Rebill_Passthrough_Service__c"][i],
            x["lcpq_Standard_vs_Non_Standard_UOM__c"][i],
            x["lcpq_Service_Code_Categorization__c"][i],
            x["Charge_Break_Flag__c"][i],
            x["Charge_Type_Code__c"][i],
            x["lcpq_Document_Service_Description__c"][i],
            x["lcpq_Catalog_Category__c"][i],
            False,
            "1",
            False,
            True,
            "Fixed Price",
            "Renewable",
            True,
            x["lcpq_DG_Boxing_Defrost_Language__c"][i],
            x["lcpq_Exclude_from_Documents__c"][i],
            "MPT",
            True,
            x["lcpq_Rollup_Category__c"][i],
            x["lcpq_Subcategory__c"][i],
            x["SBQQ__ConfigurationType__c"][i],
            x["lcpq_Per_Order_Min_Flag__c"][i],
            "None",
            True,
            True,
        ] 
    Insert_Service_Code(feature)


def Insert_Service_Code(x):
    x_copy = x.copy()
    x_copy["GearsetExternalId__c"] = ""
    Update_Data = []
    data = Formatter_For_Insert(x=x_copy)
    results = sf_conn.bulk.Product2.insert(data, batch_size=200)
    for i, result in enumerate(results):
        if result["id"] is not None:
            data[i]["id"] = result["id"]
            x_copy.at[i, "GearsetExternalId__c"] = result["id"][::-1]
            data_dict = {"id": result["id"], "GearsetExternalId__c": result["id"][::-1]}
            Update_Data.append(data_dict)
        elif results["message"] is not None:
            st.warning(f"Issue with row{i} error message {results['message']}")
    update = sf_conn.bulk.Product2.update(Update_Data, batch_size=200)
    excel_data = to_excel_buffer(x_copy)
    st.success("Service Code Load Complete")
    st.download_button(
        label="📥 Download Service Code Excel File",
        data=excel_data,
        file_name="ServiceCode.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    Create_Price_Book(data)
    Create_Tariff_Rate(data)


def Create_Price_Book(x):
    Column_header = [
        "CurrencyIsoCode",
        "IsActive",
        "Pricebook2Id",
        "Product2Id",
        "UnitPrice",
    ]
    feature = pd.DataFrame(columns=Column_header)
    for i, item in enumerate(x):
        feature.loc[len(feature.index)] = [
            "USD",
            True,
            "01s30000000FcnzAAC",
            x[i]["id"],
            0,
        ]
        feature.loc[len(feature.index)] = [
            "USD",
            True,
            "01s4Q0000004ZmLQAU",
            x[i]["id"],
            0,
        ]
        feature.loc[len(feature.index)] = [
            "CAD",
            True,
            "01s30000000FcnzAAC",
            x[i]["id"],
            0,
        ]
        feature.loc[len(feature.index)] = [
            "CAD",
            True,
            "01s4Q0000004ZmLQAU",
            x[i]["id"],
            0,
        ]
    Insert_Price_Book(feature)


def Insert_Price_Book(x):
    x_copy = x.copy()
    x_copy["GearsetExternalId__c"] = ""
    Update_Data = []
    data = Formatter_For_Insert(x=x_copy)
    results = sf_conn.bulk.PricebookEntry.insert(data, batch_size=200)
    for i, result in enumerate(results):
        data[i]["id"] = result["id"]
        x_copy.at[i, "GearsetExternalId__c"] = result["id"][::-1]
        data_dict = {"id": result["id"], "GearsetExternalId__c": result["id"][::-1]}
        Update_Data.append(data_dict)
    update = sf_conn.bulk.PricebookEntry.update(Update_Data, batch_size=200)
    excel_data = to_excel_buffer(x_copy)
    st.download_button(
        label="📥 Download PriceBook Excel File",
        data=excel_data,
        file_name="PriceBook.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.success("PriceBook Load Complete")


def Create_Tariff_Rate(x):
    Column_header = [
        "lcpq_Facility__c",
        "lcpq_Services__c",
        "lcpq_Effective_End_Date__c",
        "lcpq_Effective_Start_Date__c",
        "lcpq_Tariff__c",
        "GearsetExternalId__c",
    ]
    facility = [
        "a070c000010atetAAA",
        "a070c0000126ImAAAU",
        "a07a000000pUc3aAAC",
        "a07a000000zT7E6AAK",
        "a074Q000016aPxdQAE",
        "a07a000000pUc4OAAS",
        "a070c0000126LjKAAU",
        "a070c0000126LToAAM",
        "a070c000012Ld1NAAS",
        "a070c0000126ImKAAU",
        "a0730000002ZlFLAA0",
        "a070c0000126InSAAU",
        "a074Q000012LdF7QAK",
        "a074Q00001727N0QAI",
        "a07a000000zSbkrAAC",
        "a070c0000126ImjAAE",
        "a074Q000012DXfCQAW",
        "a074Q000017265JQAQ",
        "a07a000000pUc4GAAS",
        "a070c0000126IpJAAU",
        "a070c0000126IncAAE",
        "a070c0000126ImUAAU",
        "a07a000000pUc4SAAS",
        "a074Q000018Igm5QAC",
        "a07a000000pUc4UAAS",
        "a070c000012Ld1cAAC",
        "a070c0000126IoGAAU",
        "a070c0000126In3AAE",
        "a070c0000126ImeAAE",
        "a07a000000pUc3vAAC",
        "a074Q000014jzPWQAY",
        "a07a000000pUc3kAAC",
        "a0730000002YvtpAAC",
        "a07a000000pUc3mAAC",
        "a074Q000012LdDAQA0",
        "a07a000000pUc3oAAC",
        "a070c00000ejkQQAAY",
        "a073000000TTMnyAAH",
        "a0730000002Yvu7AAC",
        "a074Q000014knShQAI",
        "a074Q000017j71AQAQ",
        "a07a000000pUc3dAAC",
        "a074Q000013mvrSQAQ",
        "a074Q000017jlESQAY",
        "a0730000002YvtnAAC",
        "a070c0000126Io1AAE",
        "a074Q00001A27k4QAB",
        "a07a000000pUc4HAAS",
        "a070c0000126ImoAAE",
        "a074Q000012DXgsQAG",
        "a07a000000pUc42AAC",
        "a074Q000013mvrXQAQ",
        "a070c0000126IofAAE",
        "a070c0000126Ip9AAE",
        "a0730000002YvtxAAC",
        "a070c000011M0WFAA0",
        "a0730000002YvtwAAC",
        "a074Q000014n4pHQAQ",
        "a07a000000zT7DXAA0",
        "a070c0000126IouAAE",
        "a0730000002YvtqAAC",
        "a0730000002YvttAAC",
        "a0730000002ZlFMAA0",
        "a07a000000pUc3jAAC",
        "a074Q000014n4usQAA",
        "a07a000000pUc3tAAC",
        "a070c0000126L3uAAE",
        "a073000000QaciTAAR",
        "a074Q000014kwKDQAY",
        "a070c0000126Ip4AAE",
        "a0730000002YvtyAAC",
        "a070c0000126Kn8AAE",
        "a0730000002YvtlAAC",
        "a074Q000014lTrMQAU",
        "a070c0000126IopAAE",
        "a070c000010bJPTAA2",
        "a070c0000126ImFAAU",
        "a070c000010bJPOAA2",
        "a070c0000126ImyAAE",
        "a07a000000pUc49AAC",
        "a07a000000pUc4QAAS",
        "a070c0000126In8AAE",
        "a074Q000016aGcHQAU",
        "a07a000000pUc3nAAC",
        "a07a000000pUc47AAC",
        "a070c0000126IokAAE",
        "a0730000002YvtoAAC",
        "a074Q000017inilQAA",
        "a070c0000126ImPAAU",
        "a0730000002Yvu9AAC",
        "a07a000000pUc44AAC",
        "a070c0000126ImtAAE",
        "a0730000002YvtrAAC",
        "a0730000002Yvu0AAC",
        "a0730000002YvtmAAC",
        "a070c0000126Io6AAE",
        "a0730000002Yvu6AAC",
        "a0730000002Yvu2AAC",
        "a074Q000014n4upQAA",
        "a070c000010b3YkAAI",
        "a0730000002ZlFRAA0",
        "a0730000002Yvu3AAC",
        "a074Q000012DXh7QAG",
        "a070c0000126InhAAE",
        "a07a000000qZieYAAS",
        "a070c0000126IpOAAU",
        "a0730000002YvtuAAC",
        "a074Q000014k5yXQAQ",
        "a07a000000pUc3zAAC",
        "a070c0000126Im5AAE",
        "a07a000000pUc3xAAC",
        "a0730000002YvtsAAC",
        "a070c0000126IoLAAU",
        "a074Q00001727NEQAY",
        "a07a000000pUZCeAAO",
        "a07a000000pUc4MAAS",
        "a07a000000pUc3iAAC",
        "a070c0000126InNAAU",
        "a074Q00001720opQAA",
        "a0730000002YvtzAAC",
        "a070c000012LcNEAA0",
        "a070c0000126IozAAE",
        "a074Q000012LdC6QAK",
        "a070c0000126IoBAAU",
        "a0730000002Yvu5AAC",
        "a070c0000126IpEAAU",
        "a07a000000pUc48AAC",
        "a070c000012LcNJAA0",
        "a0730000002ZlFSAA0",
        "a0730000002ZlFVAA0",
        "a0730000002YvuAAAS",
        "a07a000000zT7E1AAK",
        "a070c0000126ImZAAU",
        "a07a000000pUc43AAC",
        "a07a000000pUc4VAAS",
        "a070c0000126Im0AAE",
        "a07a000000pUc4CAAS",
        "a070c0000126IoVAAU",
        "a074Q000014n4ulQAA",
        "a070c000010b3TqAAI",
        "a07a000000pUc3yAAC",
        "a07a000000pUc40AAC",
        "a070c0000126LTtAAM",
        "a074Q00001A27jtQAB",
        "a07a000000pUc4WAAS",
        "a07a000000pUc45AAC",
        "a07a000000pUc4PAAS",
        "a074Q000014lTrWQAU",
        "a07a000000zT7ELAA0",
        "a070c0000126KmyAAE",
        "a070c0000126IoaAAE",
        "a07a000000pUc46AAC",
        "a070c0000126InIAAU",
        "a07a000000zT7DhAAK",
        "a07a000000qaIGBAA2",
        "a070c0000126IpTAAU",
        "a07a000000qZXLdAAO",
        "a0730000003II1FAAW",
        "a0730000002Yvu4AAC",
        "a07a000000pUc4TAAS",
        "a07a000000pUc3lAAC",
        "a070c000010bJPJAA2",
        "a070c000010bJOQAA2",
        "a074Q000017ingfQAA",
        "a074Q000014lTrgQAE",
        "a074Q000017jnaFQAQ",
        "a074Q0000171nLnQAI",
        "a070c000010bJNwAAM",
        "a070c000010bJO6AAM",
        "a070c000010bJO1AAM",
        "a070c000010bJNrAAM",
        "a074Q000018HmlEQAS",
        "a074Q000018Hml4QAC",
        "a074Q000018HmkpQAC",
        "a074Q000018HmkzQAC",
        "a074Q000012DXgRQAW",
        "a074Q000012DXfnQAG",
        "a074Q00001720p4QAA",
        "a074Q00001720p5QAA",
        "a074Q00001720nnQAA",
        "a074Q00001720nmQAA",
        "a074Q000012DXfsQAG",
        "a074Q00001720pTQAQ",
        "a074Q000012DXhMQAW",
        "a074Q000012DXhHQAW",
        "a074Q00001AzOn0QAF",
        "a074Q00001A27k9QAB",
        "a074Q00001A27kBQAR",
        "a074Q00001A27kDQAR",
        "a074Q000012DXhRQAW",
        "a074Q000012DXh2QAG",
        "a074Q000012DXhCQAW",
        "a074Q00001727N9QAI",
        "a074Q000012DXgnQAG",
        "a074Q000012DXgxQAG",
        "a070c0000126Kn3AAE",
        "a074Q00001727MfQAI",
        "a074Q00001727MzQAI",
        "a07a000000zSbjFAAS",
        "a070c000012Ld1SAAS",
        "a070c000012Ld1XAAS",
        "a074Q000014n4uqQAA",
        "a074Q00001727JMQAY",
        "a074Q000013owk2QAA",
        "a074Q000013owjxQAA",
        "a070c0000126JRdAAM",
        "a070c000011M0cSAAS",
        "a074Q000014kvkZQAQ",
        "a070c0000126IoQAAU",
        "a07a000000pUc41AAC",
        "a07a000000pUc3eAAC",
        "a07a000000pUc3gAAC",
    ]
    feature = pd.DataFrame(columns=Column_header)
    for y in facility:
        for i, item in enumerate(x):
            feature.loc[len(feature.index)] = [
                y,
                x[i]["id"],
                "2024-12-31",
                "2024-01-01",
                9999,
                "20240101_20241231_" + y + "_" + x[i]["ProductCode"],
            ]
            feature.loc[len(feature.index)] = [
                y,
                x[i]["id"],
                "2025-12-31",
                "2025-01-01",
                9999,
                "20250101_20251231_" + y + "_" + x[i]["ProductCode"],
            ]
    Insert_Tariff_Rate(feature)


def Insert_Tariff_Rate(x):
    x_copy = x.copy()
    data = Formatter_For_Insert(x=x_copy)
    results = sf_conn.bulk.lcpq_Tariff_Rate_Table__c.insert(data, batch_size=5000)
    for i, result in enumerate(results):
        data[i]["id"] = result["id"]
    excel_data = to_excel_buffer(x_copy)
    st.download_button(
        label="📥 Download Tariff Rate Excel File",
        data=excel_data,
        file_name="ServiceCode_Upload.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.success("Tariff Rate Load Complete")

def Formatter_For_Insert(x):
    data = []
    for row in x.itertuples():
        d = row._asdict()
        del d["Index"]
        data.append(d)
    return data

