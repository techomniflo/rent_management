import frappe
import erpnext
from frappe import ValidationError, _, qb, scrub, throw
from frappe.utils import cint, comma_or, flt, getdate
from erpnext.setup.utils import get_exchange_rate
from erpnext import erpnext.accounts.doctype.payment_entry.payment_entry.get_reference_details as get_reference_details

def override_get_reference_details(doc,method):
    @frappe.whitelist()
    def override_get_reference_details(reference_doctype, reference_name, party_account_currency):
        frappe.msgprint("hello")
    get_reference_details = override_get_reference_details
    
    
    
