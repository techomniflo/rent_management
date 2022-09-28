# Copyright (c) 2022, Gourav Saini and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today
class StorePayment(Document):
	def on_cancel(self):
		payment_entry=frappe.get_doc('Payment Entry',self.invoice_payment_entry_reference)
		payment_entry.cancel()
	def on_submit(self):
		self.make_payment_entry()

	def make_payment_entry(self):
		payment_entry=frappe.new_doc('Payment Entry')
		payment_entry.posting_date=today()
		payment_entry.company=self.company
		payment_entry.payment_type='Receive'
		payment_entry.mode_of_payment='Cash'
		payment_entry.party_type='Customer'
		payment_entry.party=self.customer
		payment_entry.paid_from=self.paid_from
		payment_entry.paid_from_account_currency=self.paid_from_account_currency
		payment_entry.paid_to=self.paid_to
		payment_entry.paid_to_account_currency=self.paid_to_account_currency
		payment_entry.paid_amount=self.allocate
		payment_entry.received_amount=self.allocate
		company_currency=frappe.get_doc("Company",self.company).default_currency
		if payment_entry.paid_from_account_currency==company_currency:
			payment_entry.source_exchange_rate=1

		payment_entry.base_paid_amount=payment_entry.paid_amount*payment_entry.source_exchange_rate
		
		if payment_entry.paid_from_account_currency == payment_entry.paid_to_account_currency:
			payment_entry.target_exchange_rate=payment_entry.source_exchange_rate
			payment_entry.base_received_amount=payment_entry.base_paid_amount
		if self.invoices_reference:
			for i in self.invoices_reference:
				payment_entry.append('references',{
					'reference_doctype':i.type,
					'due_date':i.due_date,
					'reference_name':i.invoice_name,
					'total_amount':i.grand_total,
					'outstanding_amount':i.outstanding,
					'allocated_amount':i.allocated
				})
		payment_entry.save(ignore_permissions = True)
		payment_entry.submit()
		self.db_set("invoice_payment_entry_reference", payment_entry.name, update_modified=False)
		
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
		sales_invoices=frappe.db.sql("""select si.name,si.posting_date,si.rounded_total,si.outstanding_amount,si.due_date from `tabSales Invoice` as si where si.company=%(company)s and si.customer=%(customer)s and si.outstanding_amount!=0 and si.docstatus=1 order by si.posting_date;""",values=values,as_dict=True)
		for invoices in sales_invoices:
			self.append('invoices_reference',{
				'type':'Sales Invoice',
				'invoice_name':invoices.name,
				'grand_total':invoices.rounded_total,
				'outstanding':invoices.outstanding_amount,
				'due_date':invoices.due_date
			})
		rent_invoices=frappe.db.sql("""select r.name,r.grand_total,r.outstanding_amount,r.from_date,r.to_date,r.discount_type from `tabPlacement Promotion` as r where r.company=%(company)s and r.customer=%(customer)s and r.outstanding_amount!=0 and r.docstatus=1 order by r.posting_date""",values=values,as_dict=True)
		for rent in rent_invoices:
			self.append('rent_reference',{
			'type':rent.discount_type,
			'invoice_name':rent.name,
			'from_date':rent.from_date,
			'to_date':rent.to_date,
			'amount':rent.grand_total,
			'outstanding_amount':rent.outstanding_amount
			})

	@frappe.whitelist()
	def get_negative_outstanding(self):
		values={'customer':self.customer,'company':self.company}
		negative_invoices=frappe.db.sql("""select si.name from `tabSales Invoice` as si where si.outstanding_amount<0 and si.docstatus=1 and si.company=%(company)s and si.customer=%(customer)s;""",values=values)
		if len(negative_invoices)>0:
			return True
		else:
			return False