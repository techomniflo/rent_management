from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry
import frappe
import erpnext
from frappe import _
from erpnext.setup.utils import get_exchange_rate
from frappe.utils import cint, cstr, flt, get_link_to_form, getdate


class CustomPaymentEntry(PaymentEntry):
	def get_valid_reference_doctypes(self):
		if self.party_type == "Customer":
			return ("Sales Order", "Sales Invoice", "Journal Entry", "Dunning","Placement Promotion")
		elif self.party_type == "Supplier":
			return ("Purchase Order", "Purchase Invoice", "Journal Entry")
		elif self.party_type == "Shareholder":
			return ("Journal Entry",)
		elif self.party_type == "Employee":
			return ("Journal Entry",)
	def set_missing_ref_details(self, force=False):
		for d in self.get("references"):
			if d.allocated_amount:
				ref_details = get_reference_details(
					d.reference_doctype, d.reference_name, self.party_account_currency
				)

				for field, value in ref_details.items():
					if d.exchange_gain_loss:
						# for cases where gain/loss is booked into invoice
						# exchange_gain_loss is calculated from invoice & populated
						# and row.exchange_rate is already set to payment entry's exchange rate
						# refer -> `update_reference_in_payment_entry()` in utils.py
						continue

					if field == "exchange_rate" or not d.get(field) or force:
						d.db_set(field, value)
	
	def validate_allocated_amount_with_latest_data(self):
		from rent_management.rent_management.doctype_events.payment_entry import get_outstanding_reference_documents

		latest_references = get_outstanding_reference_documents(
			{
				"posting_date": self.posting_date,
				"company": self.company,
				"party_type": self.party_type,
				"payment_type": self.payment_type,
				"party": self.party,
				"party_account": self.paid_from if self.payment_type == "Receive" else self.paid_to,
				"get_outstanding_invoices": True,
				"get_orders_to_be_billed": True,
			}
		)
		

		# Group latest_references by (voucher_type, voucher_no)
		latest_lookup = {}
		for d in latest_references:
			d = frappe._dict(d)
			latest_lookup.setdefault((d.voucher_type, d.voucher_no), frappe._dict())[d.payment_term] = d

		for d in self.get("references"):
			latest = (latest_lookup.get((d.reference_doctype, d.reference_name)) or frappe._dict()).get(
				d.payment_term
			)

			# The reference has already been fully paid

			if not latest:
				frappe.throw(
					_("{0} {1} has already been fully paid.").format(_(d.reference_doctype), d.reference_name)
				)
			# The reference has already been partly paid
			elif latest.outstanding_amount < latest.invoice_amount and flt(
				d.outstanding_amount, d.precision("outstanding_amount")
			) != flt(latest.outstanding_amount, d.precision("outstanding_amount")):

				frappe.throw(
					_(
						"{0} {1} has already been partly paid. Please use the 'Get Outstanding Invoice' or the 'Get Outstanding Orders' button to get the latest outstanding amounts."
					).format(_(d.reference_doctype), d.reference_name)
				)

			fail_message = _("Row #{0}: Allocated Amount cannot be greater than outstanding amount.")

			if (flt(d.allocated_amount)) > 0 and flt(d.allocated_amount) > flt(latest.outstanding_amount):
				frappe.throw(fail_message.format(d.idx))

			if d.payment_term and (
				(flt(d.allocated_amount)) > 0
				and flt(d.allocated_amount) > flt(latest.payment_term_outstanding)
			):
				frappe.throw(
					_(
						"Row #{0}: Allocated amount:{1} is greater than outstanding amount:{2} for Payment Term {3}"
					).format(
						d.idx, d.allocated_amount, latest.payment_term_outstanding, d.payment_term
					)
				)

			# Check for negative outstanding invoices as well
			if flt(d.allocated_amount) < 0 and flt(d.allocated_amount) < flt(latest.outstanding_amount):
				frappe.throw(fail_message.format(d.idx))


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


@frappe.whitelist()
def get_reference_details(reference_doctype, reference_name, party_account_currency):
	total_amount = outstanding_amount = exchange_rate = None

	ref_doc = frappe.get_doc(reference_doctype, reference_name)
	company_currency = ref_doc.get("company_currency") or erpnext.get_company_currency(
		ref_doc.company
	)

	if reference_doctype == "Dunning":
		total_amount = outstanding_amount = ref_doc.get("dunning_amount")
		exchange_rate = 1

	elif ref_doc.doctype == "Placement Promotion":
		total_amount= ref_doc.grand_total
		outstanding_amount=ref_doc.outstanding_amount
		exchange_rate=1

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
			"bill_no": ref_doc.get("bill_no"),
		}
	)