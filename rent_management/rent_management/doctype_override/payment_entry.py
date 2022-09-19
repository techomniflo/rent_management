import frappe
import erpnext
from frappe import ValidationError, _, qb, scrub, throw
from frappe.utils import cint, comma_or, flt, getdate, 
from erpnext.setup.utils import get_exchange_rate

@frappe.whitelist()
def get_reference_details(reference_doctype, reference_name, party_account_currency):
    pass
