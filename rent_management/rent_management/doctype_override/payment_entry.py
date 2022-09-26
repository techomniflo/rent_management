import frappe
import erpnext
from frappe import ValidationError, _, qb, scrub, throw
from frappe.utils import cint, comma_or, flt, getdate
from erpnext.setup.utils import get_exchange_rate
from erpnext.accounts.doctype.payment_entry.payment_entry import get_reference_details

def on_submit(doc,method):
    for d in doc.references:
        if d.reference_doctype=="Store Credit":
            store_credit=frappe.get_doc("Store Credit",d.reference_name)
            new_outstanding_amount=d.outstanding_amount-d.allocated_amount
            if new_outstanding_amount==0 or new_outstanding_amount<0:
                frappe.msgprint(dir(d))
            frappe.db.set_value('Store Credit', d.reference_name, 'outstanding_amount', new_outstanding_amount , update_modified=False)
            frappe.db.commit()
