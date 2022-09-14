# Copyright (c) 2022, Gourav Saini and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class StorePayment(Document):
	def on_submit():
		pass
	
	@frappe.whitelist()
	def allocate_outstanding(self):
		if self.invoices_reference:
			allocate=self.allocate
			for i in self.invoices_reference:
				if allocate>=i.outstanding:
					i.allocated=i.outstanding
					allocate=allocate-i.outstanding
				else:
					i.allocated=allocate
					allocate=allocate-allocate
	
	@frappe.whitelist()
	def allocate_credit(self):
		if self.rent_reference:
			allocate=self.allocate_to_credit
			for i in self.rent_reference:
				if allocate>=i.outstanding_amount:
					i.allocate=i.outstanding_amount
					allocate=allocate-i.outstanding_amount
				else:
					i.allocate=allocate
					allocate=allocate-allocate

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
		rent_invoices=frappe.db.sql("""select r.name,r.rent,r.outstanding_amount,r.from_date,r.to_date from `tabStore Credit` as r where r.company=%(company)s and r.customer=%(customer)s and r.outstanding_amount>0 order by r.posting_date""",values=values,as_dict=True)
		for rent in rent_invoices:
			self.append('rent_reference',{
			'type':'Rent',
			'invoice_name':rent.name,
			'from_date':rent.from_date,
			'to_date':rent.to_date,
			'rent_amount':rent.amount,
			'outstanding_amount':rent.outstanding_amount
			})
