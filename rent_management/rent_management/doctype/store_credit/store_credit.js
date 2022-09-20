// Copyright (c) 2022, Gourav Saini and contributors
// For license information, please see license.txt


frappe.ui.form.on('Store Credit', {
	refresh: function(frm) {
		if(frm.doc.docstatus > 0) {
			frm.add_custom_button(__('Ledger'), function() {
				frappe.route_options = {
					"voucher_no": frm.doc.name,
					"from_date": frm.doc.posting_date,
					"to_date": moment(frm.doc.modified).format('YYYY-MM-DD'),
					"company": frm.doc.company,
					// "finance_book": frm.doc.finance_book,
					"group_by": '',
					"show_cancelled_entries": frm.doc.docstatus === 2
				};
				frappe.set_route("query-report", "General Ledger");
			}, __('View'));
	}
},
	grand_total: function(frm){
	frm.set_value('outstanding_amount',frm.doc.grand_total)
}
});

