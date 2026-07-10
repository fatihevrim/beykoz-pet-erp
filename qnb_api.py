import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import base64

# QNB e-Finans Web Services Connector URLs
EFINANS_TEST_URL = "https://test.efinans.com.tr/connector/services/ConnectorService"
EFINANS_PROD_URL = "https://connector.efinans.com.tr/connector/services/ConnectorService"

def efinans_soap_request(url, soap_action, body_xml):
    """
    Sends a direct SOAP XML request to QNB e-Finans connector service.
    This avoids dependencies on heavy SOAP libraries like zeep.
    """
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": soap_action
    }
    
    soap_envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://service.connector.efinans.com.tr">
   <soapenv:Header/>
   <soapenv:Body>
      {body_xml}
   </soapenv:Body>
</soapenv:Envelope>"""

    try:
        response = requests.post(url, data=soap_envelope.encode('utf-8'), headers=headers, timeout=15)
        return response.status_code, response.text
    except Exception as e:
        return 500, f"Bağlantı hatası: {str(e)}"

def login_efinans(username, password, use_prod=False):
    """
    Authenticates with QNB e-Finans API.
    Returns: (success_boolean, token_string_or_error_message)
    """
    url = EFINANS_PROD_URL if use_prod else EFINANS_TEST_URL
    body_xml = f"""
      <ser:login>
         <ser:wsUserName>{username}</ser:wsUserName>
         <ser:wsPassword>{password}</ser:wsPassword>
      </ser:login>
    """
    
    status, response_text = efinans_soap_request(url, "", body_xml)
    if status != 200:
        return False, f"HTTP Hatası {status}: {response_text[:300]}"
    
    try:
        # Parse SOAP Response to extract ticket
        root = ET.fromstring(response_text)
        # Handle namespaces dynamically
        namespaces = {'ns': 'http://service.connector.efinans.com.tr', 'soap': 'http://schemas.xmlsoap.org/soap/envelope/'}
        return_elem = root.find('.//loginResponse/return', namespaces)
        if return_elem is not None and return_elem.text:
            return True, return_elem.text
        
        # Alternative namespace parsing if namespace prefix varies
        for elem in root.iter():
            if elem.tag.endswith('return'):
                return True, elem.text
                
        return False, "Giriş başarısız: Yanıtta bilet (ticket) bulunamadı."
    except Exception as e:
        return False, f"XML Okuma Hatası: {str(e)}"

def get_incoming_invoices_xml(username, password, vkn, app_code, days_back=7, use_prod=False):
    """
    Logs in and fetches incoming e-Invoices from the last X days.
    Returns: (success_boolean, list_of_invoice_xmls_or_error)
    """
    # 1. Login
    login_ok, ticket = login_efinans(username, password, use_prod)
    if not login_ok:
        return False, f"QNB e-Finans Giriş Hatası: {ticket}"
        
    url = EFINANS_PROD_URL if use_prod else EFINANS_TEST_URL
    
    # 2. Query Received Invoices list
    today = datetime.now()
    start_date = (today - timedelta(days=days_back)).strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")
    
    # SOAP getReceivedInvoices XML payload
    body_xml = f"""
      <ser:getReceivedInvoices>
         <ser:ticket>{ticket}</ser:ticket>
         <ser:vkn>{vkn}</ser:vkn>
         <ser:appCode>{app_code}</ser:appCode>
         <ser:startDate>{start_date}</ser:startDate>
         <ser:endDate>{end_date}</ser:endDate>
         <ser:readState>UNREAD</ser:readState>
      </ser:getReceivedInvoices>
    """
    
    status, response_text = efinans_soap_request(url, "", body_xml)
    if status != 200:
        return False, f"Fatura listesi çekme hatası (HTTP {status}): {response_text[:300]}"
        
    try:
        root = ET.fromstring(response_text)
        
        # Parse return elements containing invoice contents (usually zip base64 encoded XML files)
        invoice_xmls = []
        
        # Finding elements with name invoiceXML or return in SOAP envelope
        for elem in root.iter():
            if elem.tag.endswith('invoiceXML') or elem.tag.endswith('xmlContent'):
                try:
                    # Decode base64 UBL XML contents if encoded
                    raw_xml = base64.b64decode(elem.text).decode('utf-8')
                    invoice_xmls.append(raw_xml)
                except Exception:
                    invoice_xmls.append(elem.text)
                    
        # In test environments or if empty, let's look for standard elements
        if not invoice_xmls:
            # Check for any long string containing UBL-TR Invoice schema indicators
            for elem in root.iter():
                if elem.text and "<Invoice" in elem.text:
                    invoice_xmls.append(elem.text)
                    
        return True, invoice_xmls
    except Exception as e:
        return False, f"XML Liste Okuma Hatası: {str(e)}"

def parse_live_ubl_invoice(ubl_xml_string):
    """
    Parses a live UBL-TR XML e-Invoice.
    Extracts cbc:Description, cbc:ID, cbc:InvoicedQuantity, and cbc:PriceAmount.
    """
    try:
        namespaces = {
            'inv': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
        }
        
        root = ET.fromstring(ubl_xml_string.encode('utf-8'))
        invoice_lines = root.findall('.//cac:InvoiceLine', namespaces)
        
        parsed_products = []
        for line in invoice_lines:
            # 1. Barcode / Stock Code (sellers id or item name identification)
            barcode_elem = line.find('.//cac:Item/cac:SellersItemIdentification/cbc:ID', namespaces)
            if barcode_elem is None:
                # Fallback to Buyers Identification
                barcode_elem = line.find('.//cac:Item/cac:BuyersItemIdentification/cbc:ID', namespaces)
            
            # Extract barcode or generate a deterministic mock code based on name if empty
            barcode = barcode_elem.text if barcode_elem is not None else None
            
            # 2. Product Name / Description
            name_elem = line.find('.//cac:Item/cbc:Name', namespaces)
            if name_elem is None:
                name_elem = line.find('.//cbc:Description', namespaces)
            name = name_elem.text if name_elem is not None else "Bilinmeyen Ürün"
            
            # If barcode is missing, make one from name so POS can use it
            if not barcode:
                barcode = f"999{abs(hash(name)) % 1000000000:010d}"
            
            # 3. Quantity
            qty_elem = line.find('.//cbc:InvoicedQuantity', namespaces)
            qty = int(float(qty_elem.text)) if qty_elem is not None else 0
            
            # 4. Wholesale Price
            price_elem = line.find('.//cac:Price/cbc:PriceAmount', namespaces)
            price = float(price_elem.text) if price_elem is not None else 0.0
            
            # Categorization
            lower_name = name.lower()
            category = "Diğer"
            if "mama" in lower_name or "kitten" in lower_name or "sterilised" in lower_name:
                category = "Köpek Maması" if "köpek" in lower_name else "Kedi Maması"
            elif "kum" in lower_name or "litter" in lower_name:
                category = "Kum"
            elif "tasma" in lower_name or "yata" in lower_name or "kap" in lower_name:
                category = "Aksesuar"
            elif "vitamin" in lower_name or "macun" in lower_name or "ödül" in lower_name:
                category = "Ödül/Vitamin"
            elif "oyuncak" in lower_name:
                category = "Oyuncak"
                
            skt = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
            gorsel_url = "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
            if "Mama" in category:
                gorsel_url = "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"
                
            parsed_products.append({
                "barkod": barcode,
                "ad": name,
                "fiyat": price,
                "miktar": qty,
                "kategori": category,
                "skt": skt,
                "gorsel_url": gorsel_url
            })
            
        return parsed_products
    except Exception as e:
        print(f"Error parsing live XML invoice: {e}")
        return []
