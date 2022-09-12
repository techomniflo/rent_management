# Copyright (c) 2022, Gourav Saini and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class StorePayment(Document):
	@frappe.whitelist()
	def fetch_items(self):
		values={'company':self.company,'customer':self.customer}
		sales_invoices=frappe.db.sql("""select si.name,si.posting_date,si.rounded_total,si.outstanding_amount,si.due_date from `tabSales Invoice` as si where si.company=%(company)s and si.customer=%(customer)s and si.outstanding_amount>0 and si.docstatus=1 and si.status!='Return' order by si.posting_date;""",values=values,as_dict=True)
		for invoices in sales_invoices:
			self.append('invoices_reference',{
				'type':'Sales Invoice',
				'invoice_name':invoices.name,
				'grand_total':invoices.rounded_total,
				'outstanding':invoices.outstanding_amount,
				'due_date':invoices.due_date
			})