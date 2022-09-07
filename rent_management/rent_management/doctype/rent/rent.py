# Copyright (c) 2022, Gourav Saini and contributors
# For license information, please see license.txt


import frappe
from frappe.model.document import Document
# from erpnext.controllers.accounts_controller import get_gl_dict
from frappe.utils import cint, cstr, flt, fmt_money, formatdate, get_link_to_form, nowdate
from erpnext.controllers.accounts_controller import AccountsController

class Rent(AccountsController):
	def __init__(self, *args, **kwargs):
		super(Rent, self).__init__(*args, **kwargs)
	def validate(self):
		pass
	def on_submit(self):
		self.makes_gl_entries()
	def on_cancel(self):
		from erpnext.accounts.general_ledger import make_reverse_gl_entries
		self.ignore_linked_doctypes = ("GL Entry")
		frappe.msgprint("in reversal function")
		make_reverse_gl_entries(voucher_type=self.doctype, voucher_no=self.name)

	def makes_gl_entries(self,cancel=0,adv_adj=0):
		from erpnext.accounts.general_ledger import make_gl_entries
		gl_map=self.build_gl_map()
		if gl_map:
			update_outstanding=0
			frappe.msgprint(str(cancel))
			make_gl_entries(gl_map, cancel=cancel, adv_adj=adv_adj, update_outstanding=update_outstanding)
	def build_gl_map(self):
		gl_map=[]
		frappe.msgprint(str(gl_map))
		gl_map.append(
			self.get_gl_dict(
						{
							"account": 'Debtors - OS',
							"party_type": "Customer",
							"party": self.customer,
							"against": 'Marketing Expenses - OS',
							"credit": self.rent,
                            "company": 'Omnipresent Services',
							"account_currency": 'INR',
							"credit_in_account_currency": self.rent,
							# "against_voucher_type": 'Rent',
							# "against_voucher": self.name,
							"remarks": "Rent collected",
							"cost_center": 'Main - OS'
						},
						item=self
					)
		)
		gl_map.append(
			self.get_gl_dict(
						{
							"account": 'Marketing Expenses - OS',
							"party_type": "",
							"party": "",
							"against": self.customer,
							"debit": self.rent,
                            "company": 'Omnipresent Services',
							"account_currency": 'INR',
							"debit_in_account_currency": self.rent,
							# "against_voucher_type": 'Rent',
							# "against_voucher": self.name,
							"remarks": "",
							"cost_center": 'Main - OS'
						},
						item=self
					)
		)
		# frappe.msgprint(str(gl_map))
		return gl_map
		