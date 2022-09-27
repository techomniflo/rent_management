import frappe
import erpnext
from frappe import ValidationError, _, qb, scrub, throw
from frappe.utils import cint, comma_or, flt, getdate
from erpnext.setup.utils import get_exchange_rate
from erpnext.accounts.doctype.payment_entry.payment_entry import get_reference_details
from six import iteritems, string_types
from erpnext.hr.doctype.expense_claim.expense_claim import (
	get_outstanding_amount_for_claim,
	update_reimbursed_amount,
)

def on_submit(doc,method):
    store_credit_outstanding(doc,method,cancel=False)
    update_outstanding_amounts(doc,method)

def before_cancel(doc,method):
    store_credit_outstanding(doc,method,cancel=True)

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