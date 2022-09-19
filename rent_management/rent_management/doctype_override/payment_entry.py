import frappe
import erpnext
from frappe import ValidationError, _, qb, scrub, throw
from frappe.utils import cint, comma_or, flt, getdate, 
from erpnext.setup.utils import get_exchange_rate

@frappe.whitelist()
def get_reference_details(reference_doctype, reference_name, party_account_currency):
    frappe.msgprint("hello")
	total_amount = outstanding_amount = exchange_rate = None

	ref_doc = frappe.get_doc(reference_doctype, reference_name)
	company_currency = ref_doc.get("company_currency") or erpnext.get_company_currency(
		ref_doc.company
	)

	if reference_doctype == "Dunning":
		total_amount = outstanding_amount = ref_doc.get("dunning_amount")
		exchange_rate = 1

	elif reference_doctype == "Journal Entry" and ref_doc.docstatus == 1:
		total_amount = ref_doc.get("total_amount")
		if ref_doc.multi_currency:
			exchange_rate = get_exchange_rate(
				party_account_currency, company_currency, ref_doc.posting_date
			)
		else:
			exchange_rate = 1
			outstanding_amount = get_outstanding_on_journal_entry(reference_name)

	elif reference_doctype != "Journal Entry":
		if not total_amount:
			if party_account_currency == company_currency:
				# for handling cases that don't have multi-currency (base field)
				total_amount = ref_doc.get("grand_total") or ref_doc.get("base_grand_total")
				exchange_rate = 1
			else:
				total_amount = ref_doc.get("grand_total")
		if not exchange_rate:
			# Get the exchange rate from the original ref doc
			# or get it based on the posting date of the ref doc.
			exchange_rate = ref_doc.get("conversion_rate") or get_exchange_rate(
				party_account_currency, company_currency, ref_doc.posting_date
			)

		if reference_doctype in ("Sales Invoice", "Purchase Invoice"):
			outstanding_amount = ref_doc.get("outstanding_amount")
		else:
			outstanding_amount = flt(total_amount) - flt(ref_doc.get("advance_paid"))

	else:
		# Get the exchange rate based on the posting date of the ref doc.
		exchange_rate = get_exchange_rate(party_account_currency, company_currency, ref_doc.posting_date)

	return frappe._dict(
		{
			"due_date": ref_doc.get("due_date"),
			"total_amount": flt(total_amount),
			"outstanding_amount": flt(outstanding_amount),
			"exchange_rate": flt(exchange_rate),
			"bill_no": ref_doc.get("bill_no"),
		}
	)


def get_outstanding_on_journal_entry(name):
	res = frappe.db.sql(
		"SELECT "
		'CASE WHEN party_type IN ("Customer") '
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
