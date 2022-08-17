# Copyright (c) 2022, Gourav Saini and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class StorePaymentCalculator(Document):
	@frappe.whitelist()
	def fetch_items(self):
		total=0
		sales_invoices=frappe.db.get_all('Sales Invoice',filters={'customer':self.customer},fields=['customer','name','posting_date','outstanding_amount'])
		for invoices in sales_invoices:
			total=total+invoices['outstanding_amount']
			self.append('items',
			{'receipt':invoices['name'],
			'posting_date':invoices['posting_date'],
			'amount':invoices['outstanding_amount'],
			'total':total,
			})



