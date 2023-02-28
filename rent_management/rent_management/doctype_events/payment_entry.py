import frappe
import erpnext
import json
from erpnext.accounts.party import get_party_account
from erpnext.accounts.utils import get_account_currency, get_balance_on, get_outstanding_invoices
from frappe import ValidationError, _, qb, scrub, throw
from frappe.utils import cint, comma_or, flt, getdate, nowdate
from erpnext.setup.utils import get_exchange_rate
from erpnext.accounts.doctype.payment_entry.payment_entry import get_reference_details
from six import iteritems, string_types
from erpnext.controllers.accounts_controller import (
	AccountsController,
	get_supplier_block_status,
	validate_taxes_and_charges,
)
from erpnext.accounts.doctype.invoice_discounting.invoice_discounting import (
	get_party_account_based_on_invoice_discounting,
)

def on_submit(doc,method):
	store_credit_outstanding(doc,method,cancel=False)
	doc.update_outstanding_amounts()
	
	

def on_cancel(doc,method):
	store_credit_outstanding(doc,method,cancel=True)
	doc.update_outstanding_amounts()



def store_credit_outstanding(doc,mehtod,cancel):
	for d in doc.references:
		if d.reference_doctype=="Placement Promotion":
			store_credit=frappe.get_doc("Placement Promotion",d.reference_name)
			if cancel:
				new_outstanding_amount=store_credit.outstanding_amount+d.allocated_amount
			else:
				new_outstanding_amount=store_credit.outstanding_amount-d.allocated_amount
			frappe.db.set_value('Placement Promotion', d.reference_name, 'outstanding_amount', new_outstanding_amount , update_modified=False)
			frappe.db.commit()

@frappe.whitelist()
def get_outstanding_reference_documents(args):
	if isinstance(args, str):
		args = json.loads(args)

	if args.get("party_type") == "Member":
		return

	ple = qb.DocType("Payment Ledger Entry")
	common_filter = []
	accounting_dimensions_filter = []
	posting_and_due_date = []

	# confirm that Supplier is not blocked
	if args.get("party_type") == "Supplier":
		supplier_status = get_supplier_block_status(args["party"])
		if supplier_status["on_hold"]:
			if supplier_status["hold_type"] == "All":
				return []
			elif supplier_status["hold_type"] == "Payments":
				if (
					not supplier_status["release_date"] or getdate(nowdate()) <= supplier_status["release_date"]
				):
					return []

	party_account_currency = get_account_currency(args.get("party_account"))
	company_currency = frappe.get_cached_value("Company", args.get("company"), "default_currency")

	# Get positive outstanding sales /purchase invoices
	condition = ""
	if args.get("voucher_type") and args.get("voucher_no"):
		condition = " and voucher_type={0} and voucher_no={1}".format(
			frappe.db.escape(args["voucher_type"]), frappe.db.escape(args["voucher_no"])
		)
		common_filter.append(ple.voucher_type == args["voucher_type"])
		common_filter.append(ple.voucher_no == args["voucher_no"])

	# Add cost center condition
	if args.get("cost_center"):
		condition += " and cost_center='%s'" % args.get("cost_center")
		accounting_dimensions_filter.append(ple.cost_center == args.get("cost_center"))

	date_fields_dict = {
		"posting_date": ["from_posting_date", "to_posting_date"],
		"due_date": ["from_due_date", "to_due_date"],
	}

	for fieldname, date_fields in date_fields_dict.items():
		if args.get(date_fields[0]) and args.get(date_fields[1]):
			condition += " and {0} between '{1}' and '{2}'".format(
				fieldname, args.get(date_fields[0]), args.get(date_fields[1])
			)
			posting_and_due_date.append(ple[fieldname][args.get(date_fields[0]) : args.get(date_fields[1])])

	if args.get("company"):
		condition += " and company = {0}".format(frappe.db.escape(args.get("company")))
		common_filter.append(ple.company == args.get("company"))

	if args.get("party_type") == "Customer":
		return get_customer_outstanding(args.get("party_type"),
		args.get("party"),
		args.get("company"),
		args.get("party_account"))
	
	outstanding_invoices = get_outstanding_invoices(
		args.get("party_type"),
		args.get("party"),
		args.get("party_account"),
		common_filter=common_filter,
		posting_date=posting_and_due_date,
		min_outstanding=args.get("outstanding_amt_greater_than"),
		max_outstanding=args.get("outstanding_amt_less_than"),
		accounting_dimensions=accounting_dimensions_filter,
	)

	outstanding_invoices = split_invoices_based_on_payment_terms(outstanding_invoices)

	for d in outstanding_invoices:
		d["exchange_rate"] = 1
		if party_account_currency != company_currency:
			if d.voucher_type in frappe.get_hooks("invoice_doctypes"):
				d["exchange_rate"] = frappe.db.get_value(d.voucher_type, d.voucher_no, "conversion_rate")
			elif d.voucher_type == "Journal Entry":
				d["exchange_rate"] = get_exchange_rate(
					party_account_currency, company_currency, d.posting_date
				)
		if d.voucher_type in ("Purchase Invoice"):
			d["bill_no"] = frappe.db.get_value(d.voucher_type, d.voucher_no, "bill_no")

	# Get all SO / PO which are not fully billed or against which full advance not paid
	orders_to_be_billed = []
	orders_to_be_billed = get_orders_to_be_billed(
		args.get("posting_date"),
		args.get("party_type"),
		args.get("party"),
		args.get("company"),
		party_account_currency,
		company_currency,
		filters=args,
	)

	# Get negative outstanding sales /purchase invoices
	negative_outstanding_invoices = []
	if args.get("party_type") != "Employee" and not args.get("voucher_no"):
		negative_outstanding_invoices = get_negative_outstanding_invoices(
			args.get("party_type"),
			args.get("party"),
			args.get("party_account"),
			party_account_currency,
			company_currency,
			condition=condition,
		)

	data = negative_outstanding_invoices + outstanding_invoices + orders_to_be_billed

	if not data:
		frappe.msgprint(
			_(
				"No outstanding invoices found for the {0} {1} which qualify the filters you have specified."
			).format(_(args.get("party_type")).lower(), frappe.bold(args.get("party")))
		)

	return data

def split_invoices_based_on_payment_terms(outstanding_invoices):
	invoice_ref_based_on_payment_terms = {}
	for idx, d in enumerate(outstanding_invoices):
		if d.voucher_type in ["Sales Invoice", "Purchase Invoice"]:
			payment_term_template = frappe.db.get_value(
				d.voucher_type, d.voucher_no, "payment_terms_template"
			)
			if payment_term_template:
				allocate_payment_based_on_payment_terms = frappe.db.get_value(
					"Payment Terms Template", payment_term_template, "allocate_payment_based_on_payment_terms"
				)
				if allocate_payment_based_on_payment_terms:
					payment_schedule = frappe.get_all(
						"Payment Schedule", filters={"parent": d.voucher_no}, fields=["*"]
					)

					for payment_term in payment_schedule:
						if payment_term.outstanding > 0.1:
							invoice_ref_based_on_payment_terms.setdefault(idx, [])
							invoice_ref_based_on_payment_terms[idx].append(
								frappe._dict(
									{
										"due_date": d.due_date,
										"currency": d.currency,
										"voucher_no": d.voucher_no,
										"voucher_type": d.voucher_type,
										"posting_date": d.posting_date,
										"invoice_amount": flt(d.invoice_amount),
										"outstanding_amount": flt(d.outstanding_amount),
										"payment_amount": payment_term.payment_amount,
										"payment_term": payment_term.payment_term,
									}
								)
							)

	outstanding_invoices_after_split = []
	if invoice_ref_based_on_payment_terms:
		for idx, ref in invoice_ref_based_on_payment_terms.items():
			voucher_no = ref[0]["voucher_no"]
			voucher_type = ref[0]["voucher_type"]

			frappe.msgprint(
				_("Spliting {} {} into {} row(s) as per Payment Terms").format(
					voucher_type, voucher_no, len(ref)
				),
				alert=True,
			)

			outstanding_invoices_after_split += invoice_ref_based_on_payment_terms[idx]

			existing_row = list(filter(lambda x: x.get("voucher_no") == voucher_no, outstanding_invoices))
			index = outstanding_invoices.index(existing_row[0])
			outstanding_invoices.pop(index)

	outstanding_invoices_after_split += outstanding_invoices
	return outstanding_invoices_after_split


def get_orders_to_be_billed(
	posting_date,
	party_type,
	party,
	company,
	party_account_currency,
	company_currency,
	cost_center=None,
	filters=None,
):
	if party_type == "Customer":
		voucher_type = "Sales Order"
	elif party_type == "Supplier":
		voucher_type = "Purchase Order"
	elif party_type == "Employee":
		voucher_type = None

	# Add cost center condition
	if voucher_type:
		doc = frappe.get_doc({"doctype": voucher_type})
		condition = ""
		if doc and hasattr(doc, "cost_center"):
			condition = " and cost_center='%s'" % cost_center

	orders = []
	if voucher_type:
		if party_account_currency == company_currency:
			grand_total_field = "base_grand_total"
			rounded_total_field = "base_rounded_total"
		else:
			grand_total_field = "grand_total"
			rounded_total_field = "rounded_total"

		orders = frappe.db.sql(
			"""
			select
				name as voucher_no,
				if({rounded_total_field}, {rounded_total_field}, {grand_total_field}) as invoice_amount,
				(if({rounded_total_field}, {rounded_total_field}, {grand_total_field}) - advance_paid) as outstanding_amount,
				transaction_date as posting_date
			from
				`tab{voucher_type}`
			where
				{party_type} = %s
				and docstatus = 1
				and company = %s
				and ifnull(status, "") != "Closed"
				and if({rounded_total_field}, {rounded_total_field}, {grand_total_field}) > advance_paid
				and abs(100 - per_billed) > 0.01
				{condition}
			order by
				transaction_date, name
		""".format(
				**{
					"rounded_total_field": rounded_total_field,
					"grand_total_field": grand_total_field,
					"voucher_type": voucher_type,
					"party_type": scrub(party_type),
					"condition": condition,
				}
			),
			(party, company),
			as_dict=True,
		)

	order_list = []
	for d in orders:
		if not (
			flt(d.outstanding_amount) >= flt(filters.get("outstanding_amt_greater_than"))
			and flt(d.outstanding_amount) <= flt(filters.get("outstanding_amt_less_than"))
		):
			continue

		d["voucher_type"] = voucher_type
		# This assumes that the exchange rate required is the one in the SO
		d["exchange_rate"] = get_exchange_rate(party_account_currency, company_currency, posting_date)
		order_list.append(d)

	return order_list


def get_negative_outstanding_invoices(
	party_type,
	party,
	party_account,
	party_account_currency,
	company_currency,
	cost_center=None,
	condition=None,
):
	voucher_type = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
	supplier_condition = ""
	if voucher_type == "Purchase Invoice":
		supplier_condition = "and (release_date is null or release_date <= CURRENT_DATE)"
	if party_account_currency == company_currency:
		grand_total_field = "base_grand_total"
		rounded_total_field = "base_rounded_total"
	else:
		grand_total_field = "grand_total"
		rounded_total_field = "rounded_total"

	return frappe.db.sql(
		"""
		select
			"{voucher_type}" as voucher_type, name as voucher_no,
			if({rounded_total_field}, {rounded_total_field}, {grand_total_field}) as invoice_amount,
			outstanding_amount, posting_date,
			due_date, conversion_rate as exchange_rate
		from
			`tab{voucher_type}`
		where
			{party_type} = %s and {party_account} = %s and docstatus = 1 and
			outstanding_amount < 0
			{supplier_condition}
			{condition}
		order by
			posting_date, name
		""".format(
			**{
				"supplier_condition": supplier_condition,
				"condition": condition,
				"rounded_total_field": rounded_total_field,
				"grand_total_field": grand_total_field,
				"voucher_type": voucher_type,
				"party_type": scrub(party_type),
				"party_account": "debit_to" if party_type == "Customer" else "credit_to",
				"cost_center": cost_center,
			}
		),
		(party, party_account),
		as_dict=True,
	)

def get_customer_outstanding(party_type,party,company,party_account):
	values={'company':company,'customer':party}
	sales_invoices=frappe.db.sql("""select 'Sales Invoice' as 'voucher_type',si.name as 'voucher_no',si.posting_date,si.rounded_total as 'invoice_amount',si.outstanding_amount as 'outstanding_amount',si.due_date,'INR' as 'currency', 1 as 'exchange_rate' from `tabSales Invoice` as si where si.company=%(company)s and si.customer=%(customer)s and si.outstanding_amount!=0 and si.docstatus=1 order by si.posting_date;""",values=values,as_dict=True)
	rent_invoices=frappe.db.sql("""select 'Placement Promotion' as 'voucher_type',r.name as	'voucher_no',r.grand_total as 'invoice_amount',r.outstanding_amount as 'outstanding_amount','INR' as 'currency',1 as 'exchange_rate' from `tabPlacement Promotion` as r where r.company=%(company)s and r.customer=%(customer)s and r.outstanding_amount!=0 and r.docstatus=1 order by r.posting_date""",values=values,as_dict=True)
	for i in rent_invoices:
		i['due_date']=None
	return sales_invoices+rent_invoices