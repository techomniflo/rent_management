// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Payment Entry', {
	validate_reference_document: function(frm, row) {
		var _validate = function(i, row) {
			if (!row.reference_doctype) {
				return;
			}

			if(frm.doc.party_type=="Customer" &&
				!in_list(["Sales Order", "Sales Invoice", "Journal Entry", "Dunning", "Placement Promotion"], row.reference_doctype)
			) {
				frappe.model.set_value(row.doctype, row.name, "reference_doctype", null);
				frappe.msgprint(__("Row #{0}: Reference Document Type must be one of Sales Order, Sales Invoice, Journal Entry or Dunning and Placement Promotion", [row.idx]));
				return false;
			}

			if(frm.doc.party_type=="Supplier" &&
				!in_list(["Purchase Order", "Purchase Invoice", "Journal Entry"], row.reference_doctype)
			) {
				frappe.model.set_value(row.doctype, row.name, "against_voucher_type", null);
				frappe.msgprint(__("Row #{0}: Reference Document Type must be one of Purchase Order, Purchase Invoice or Journal Entry or Placement Promotion", [row.idx]));
				return false;
			}

			if(frm.doc.party_type=="Employee" &&
				!in_list(["Expense Claim", "Journal Entry"], row.reference_doctype)
			) {
				frappe.model.set_value(row.doctype, row.name, "against_voucher_type", null);
				frappe.msgprint(__("Row #{0}: Reference Document Type must be one of Expense Claim or Journal Entry", [row.idx]));
				return false;
			}

			if (frm.doc.party_type == "Donor" && row.reference_doctype != "Donation") {
				frappe.model.set_value(row.doctype, row.name, "reference_doctype", null);
				frappe.msgprint(__("Row #{0}: Reference Document Type must be Donation", [row.idx]));
				return false;
			}
		}

		if (row) {
			_validate(0, row);
		} else {
			$.each(frm.doc.vouchers || [], _validate);
		}
	},
	setup: function(frm) {
		frm.set_query("reference_doctype", "references", function() {
			if (frm.doc.party_type == "Customer") {
				var doctypes = ["Sales Order", "Sales Invoice", "Journal Entry", "Dunning","Placement Promotion"];
			} else if (frm.doc.party_type == "Supplier") {
				var doctypes = ["Purchase Order", "Purchase Invoice", "Journal Entry"];
			} else if (frm.doc.party_type == "Employee") {
				var doctypes = ["Expense Claim", "Journal Entry"];
			} else if (frm.doc.party_type == "Student") {
				var doctypes = ["Fees"];
			} else if (frm.doc.party_type == "Donor") {
				var doctypes = ["Donation"];
			} else {
				var doctypes = ["Journal Entry"];
			}

			return {
				filters: { "name": ["in", doctypes] }
			};
		});

		frm.set_query("reference_name", "references", function(doc, cdt, cdn) {
			const child = locals[cdt][cdn];
			const filters = {"docstatus": 1, "company": doc.company};
			const party_type_doctypes = ['Sales Invoice', 'Sales Order', 'Purchase Invoice',
				'Purchase Order', 'Expense Claim', 'Fees', 'Dunning', 'Donation','Placement Promotion'];

			if (in_list(party_type_doctypes, child.reference_doctype)) {
				filters[doc.party_type.toLowerCase()] = doc.party;
			}

			if(child.reference_doctype == "Expense Claim") {
				filters["docstatus"] = 1;
				filters["is_paid"] = 0;
			}

			return {
				filters: filters
			};
		});

	}
});	