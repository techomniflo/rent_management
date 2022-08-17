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
		customer_name=frappe.db.get_value('Customer',self.customer,'customer_name')
		values={'customer_name':customer_name}
		journal_entry=frappe.db.sql("""select je.name,je.posting_date,je.total_credit from `tabJournal Entry` as je where je.title=%(customer_name)s """,values=values,as_dict=True)
		for entry in journal_entry:
			total=total-entry['total_credit']
			self.append('items',{
				'receipt':entry['name'],
				'posting_date':entry['posting_date'],
				'amount':-1*(float(entry['total_credit'])),
				'total_amount':total})