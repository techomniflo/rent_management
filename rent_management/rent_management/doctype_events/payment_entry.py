import frappe
import erpnext
from erpnext.accounts.party import get_party_account
from erpnext.accounts.utils import get_account_currency, get_balance_on, get_outstanding_invoices
from frappe import ValidationError, _, qb, scrub, throw
from frappe.utils import cint, comma_or, flt, getdate
from erpnext.setup.utils import get_exchange_rate
from erpnext.accounts.doctype.payment_entry.payment_entry import get_reference_details
from six import iteritems, string_types
from erpnext.hr.doctype.expense_claim.expense_claim import (
	get_outstanding_amount_for_claim,
	update_reimbursed_amount,
)
from erpnext.accounts.doctype.invoice_discounting.invoice_discounting import (
	get_party_account_based_on_invoice_discounting,
)

def validate(doc,method):
	set_missing_values(doc)
	validate_reference_documents(doc)

def before_submit(doc,method):
    store_credit_outstanding(doc,method,cancel=False)

def before_cancel(doc,method):
    store_credit_outstanding(doc,method,cancel=True)

def on_submit(doc,method):
    update_outstanding_amounts(doc,method)

def on_cancel(doc,method):
    update_outstanding_amounts(doc,method)


def update_outstanding_amounts(doc,method):
		set_missing_ref_details(doc,force=True)


def set_missing_ref_details(self, force=False):
    for d in self.get("references"):
        if d.allocated_amount:
            ref_details = get_reference_details(
                d.reference_doctype, d.reference_name, self.party_account_currency
            )

            for field, value in iteritems(ref_details):
                if d.exchange_gain_loss:
                    # for cases where gain/loss is booked into invoice
                    # exchange_gain_loss is calculated from invoice & populated
                    # and row.exchange_rate is already set to payment entry's exchange rate
                    # refer -> `update_reference_in_payment_entry()` in utils.py
                    continue

                if field == "exchange_rate" or not d.get(field) or force:
                    d.db_set(field, value)



def store_credit_outstanding(doc,mehtod,cancel):
    for d in doc.references:
        if d.reference_doctype=="Store Credit":
            store_credit=frappe.get_doc("Store Credit",d.reference_name)
            if cancel:
                new_outstanding_amount=d.outstanding_amount+d.allocated_amount
            else:
                new_outstanding_amount=d.outstanding_amount-d.allocated_amount
            if new_outstanding_amount==0 or new_outstanding_amount<0:
                # frappe.msgprint(dir(d))
                frappe.db.set_value('Store Credit', d.reference_name, 'outstanding_amount', new_outstanding_amount , update_modified=False)
                frappe.db.commit()

@frappe.whitelist()
def get_reference_details(reference_doctype, reference_name, party_account_currency):
	total_amount = outstanding_amount = exchange_rate = bill_no = None
	ref_doc = frappe.get_doc(reference_doctype, reference_name)
	company_currency = ref_doc.get("company_currency") or erpnext.get_company_currency(
		ref_doc.company
	)

	if reference_doctype == "Fees":
		total_amount = ref_doc.get("grand_total")
		exchange_rate = 1
		outstanding_amount = ref_doc.get("outstanding_amount")
	elif reference_doctype == "Donation":
		total_amount = ref_doc.get("amount")
		outstanding_amount = total_amount
		exchange_rate = 1
	elif reference_doctype == "Dunning":
		total_amount = ref_doc.get("dunning_amount")
		exchange_rate = 1
		outstanding_amount = ref_doc.get("dunning_amount")
	elif reference_doctype == "Journal Entry" and ref_doc.docstatus == 1:
		total_amount = ref_doc.get("total_amount")
		if ref_doc.multi_currency:
			exchange_rate = get_exchange_rate(
				party_account_currency, company_currency, ref_doc.posting_date
			)
		else:
			exchange_rate = 1
			outstanding_amount = get_outstanding_on_journal_entry(reference_name)
	elif ref_doc.doctype == "Store Credit":
			total_amount= ref_doc.grand_total
			outstanding_amount=ref_doc.outstanding_amount
			exchange_rate=1
			# bill_no=ref_doc.name
	elif reference_doctype != "Journal Entry":
		if ref_doc.doctype == "Expense Claim":
			total_amount = flt(ref_doc.total_sanctioned_amount) + flt(ref_doc.total_taxes_and_charges)
		elif ref_doc.doctype == "Employee Advance":
			total_amount = ref_doc.advance_amount
			exchange_rate = ref_doc.get("exchange_rate")
			if party_account_currency != ref_doc.currency:
				total_amount = flt(total_amount) * flt(exchange_rate)
		elif ref_doc.doctype == "Gratuity":
			total_amount = ref_doc.amount
		
		if not total_amount:
			if party_account_currency == company_currency:
				total_amount = ref_doc.base_grand_total
				exchange_rate = 1
			else:
				total_amount = ref_doc.grand_total
		if not exchange_rate:
			# Get the exchange rate from the original ref doc
			# or get it based on the posting date of the ref doc.
			exchange_rate = ref_doc.get("conversion_rate") or get_exchange_rate(
				party_account_currency, company_currency, ref_doc.posting_date
			)
		if reference_doctype in ("Sales Invoice", "Purchase Invoice"):
			outstanding_amount = ref_doc.get("outstanding_amount")
			bill_no = ref_doc.get("bill_no")
		elif reference_doctype == "Expense Claim":
			outstanding_amount = get_outstanding_amount_for_claim(ref_doc)
		elif reference_doctype == "Employee Advance":
			outstanding_amount = flt(ref_doc.advance_amount) - flt(ref_doc.paid_amount)
			if party_account_currency != ref_doc.currency:
				outstanding_amount = flt(outstanding_amount) * flt(exchange_rate)
				if party_account_currency == company_currency:
					exchange_rate = 1
		elif reference_doctype == "Gratuity":
			outstanding_amount = ref_doc.amount - flt(ref_doc.paid_amount)
		else:
			outstanding_amount = flt(total_amount) - flt(ref_doc.advance_paid)
	else:
		# Get the exchange rate based on the posting date of the ref doc.
		exchange_rate = get_exchange_rate(party_account_currency, company_currency, ref_doc.posting_date)

	return frappe._dict(
		{
			"due_date": ref_doc.get("due_date"),
			"total_amount": flt(total_amount),
			"outstanding_amount": flt(outstanding_amount),
			"exchange_rate": flt(exchange_rate),
			"bill_no": bill_no,
		}
	)

def get_outstanding_on_journal_entry(name):
	res = frappe.db.sql(
		"SELECT "
		'CASE WHEN party_type IN ("Customer", "Student") '
		"THEN ifnull(sum(debit_in_account_currency - credit_in_account_currency), 0) "
		"ELSE ifnull(sum(credit_in_account_currency - debit_in_account_currency), 0) "
		"END as outstanding_amount "
		"FROM `tabGL Entry` WHERE (voucher_no=%s OR against_voucher=%s) "
		"AND party_type IS NOT NULL "
		'AND party_type != ""',
		(name, name),
		as_dict=1,
	)

	outstanding_amount = res[0].get("outstanding_amount", 0) if res else 0

	return outstanding_amount

@frappe.whitelist()
def get_account_details(account, date, cost_center=None):
	frappe.has_permission("Payment Entry", throw=True)

	# to check if the passed account is accessible under reference doctype Payment Entry
	account_list = frappe.get_list(
		"Account", {"name": account}, reference_doctype="Payment Entry", limit=1
	)

	# There might be some user permissions which will allow account under certain doctypes
	# except for Payment Entry, only in such case we should throw permission error
	if not account_list:
		frappe.throw(_("Account: {0} is not permitted under Payment Entry").format(account))

	account_balance = get_balance_on(
		account, date, cost_center=cost_center, ignore_account_permission=True
	)

	return frappe._dict(
		{
			"account_currency": get_account_currency(account),
			"account_balance": account_balance,
			"account_type": frappe.db.get_value("Account", account, "account_type"),
		}
	)


def set_missing_values(self):
	if self.payment_type == "Internal Transfer":
		for field in (
			"party",
			"party_balance",
			"total_allocated_amount",
			"base_total_allocated_amount",
			"unallocated_amount",
		):
			self.set(field, None)
		self.references = []
	else:
		if not self.party_type:
			frappe.throw(_("Party Type is mandatory"))

		if not self.party:
			frappe.throw(_("Party is mandatory"))

		_party_name = (
			"title" if self.party_type in ("Student", "Shareholder") else self.party_type.lower() + "_name"
		)
		self.party_name = frappe.db.get_value(self.party_type, self.party, _party_name)

	if self.party:
		if not self.party_balance:
			self.party_balance = get_balance_on(
				party_type=self.party_type, party=self.party, date=self.posting_date, company=self.company
			)

		if not self.party_account:
			party_account = get_party_account(self.party_type, self.party, self.company)
			self.set(self.party_account_field, party_account)
			self.party_account = party_account

	if self.paid_from and not (self.paid_from_account_currency or self.paid_from_account_balance):
		acc = get_account_details(self.paid_from, self.posting_date, self.cost_center)
		self.paid_from_account_currency = acc.account_currency
		self.paid_from_account_balance = acc.account_balance

	if self.paid_to and not (self.paid_to_account_currency or self.paid_to_account_balance):
		acc = get_account_details(self.paid_to, self.posting_date, self.cost_center)
		self.paid_to_account_currency = acc.account_currency
		self.paid_to_account_balance = acc.account_balance

	self.party_account_currency = (
		self.paid_from_account_currency
		if self.payment_type == "Receive"
		else self.paid_to_account_currency
	)

	set_missing_ref_details(self)
	
def validate_reference_documents(self):
	if self.party_type == "Student":
		valid_reference_doctypes = ("Fees", "Journal Entry")
	elif self.party_type == "Customer":
		valid_reference_doctypes = ("Sales Order", "Sales Invoice", "Journal Entry", "Dunning","Credit Note")
	elif self.party_type == "Supplier":
		valid_reference_doctypes = ("Purchase Order", "Purchase Invoice", "Journal Entry")
	elif self.party_type == "Employee":
		valid_reference_doctypes = ("Expense Claim", "Journal Entry", "Employee Advance", "Gratuity")
	elif self.party_type == "Shareholder":
		valid_reference_doctypes = "Journal Entry"
	elif self.party_type == "Donor":
		valid_reference_doctypes = "Donation"

	for d in self.get("references"):
		if not d.allocated_amount:
			continue
		if d.reference_doctype not in valid_reference_doctypes:
			frappe.throw(
				_("Reference Doctype must be one of {0}").format(comma_or(valid_reference_doctypes))
			)

		elif d.reference_name:
			if not frappe.db.exists(d.reference_doctype, d.reference_name):
				frappe.throw(_("{0} {1} does not exist").format(d.reference_doctype, d.reference_name))
			else:
				ref_doc = frappe.get_doc(d.reference_doctype, d.reference_name)

				if d.reference_doctype != "Journal Entry":
					if self.party != ref_doc.get(scrub(self.party_type)):
						frappe.throw(
							_("{0} {1} is not associated with {2} {3}").format(
								d.reference_doctype, d.reference_name, self.party_type, self.party
							)
						)
				else:
					self.validate_journal_entry()

				if d.reference_doctype in ("Sales Invoice", "Purchase Invoice", "Expense Claim", "Fees"):
					if self.party_type == "Customer":
						ref_party_account = (
							get_party_account_based_on_invoice_discounting(d.reference_name) or ref_doc.debit_to
						)
					elif self.party_type == "Student":
						ref_party_account = ref_doc.receivable_account
					elif self.party_type == "Supplier":
						ref_party_account = ref_doc.credit_to
					elif self.party_type == "Employee":
						ref_party_account = ref_doc.payable_account

					if ref_party_account != self.party_account:
						frappe.throw(
							_("{0} {1} is associated with {2}, but Party Account is {3}").format(
								d.reference_doctype, d.reference_name, ref_party_account, self.party_account
							)
						)

					if ref_doc.doctype == "Purchase Invoice" and ref_doc.get("on_hold"):
						frappe.throw(
							_("{0} {1} is on hold").format(d.reference_doctype, d.reference_name),
							title=_("Invalid Invoice"),
						)

				if ref_doc.docstatus != 1:
					frappe.throw(_("{0} {1} must be submitted").format(d.reference_doctype, d.reference_name))