# Copyright (c) 2022, Gourav Saini and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class StorePaymentCalculator(Document):
	@frappe.whitelist()
	def fetch_items(self):
		total=0
		values={'customer':self.customer}
		sales_invoices=frappe.db.sql("""select si.name,si.posting_date,si.rounded_total from `tabSales Invoice` as si where si.status!='Cancelled' and si.status!='Draft' and si.customer=%(customer)s order by si.posting_date""",values=values,as_dict=True)
		for invoices in sales_invoices:
			total=total+invoices['rounded_total']
			self.append('items',
			{'receipt':invoices['name'],
			'posting_date':invoices['posting_date'],
			'amount':invoices['rounded_total'],
			'total_amount':total})



