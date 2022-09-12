// Copyright (c) 2022, Gourav Saini and contributors
// For license information, please see license.txt

frappe.ui.form.on('Store Payment', {
	// refresh: function(frm) {

	// }
	get_outstanding(frm){
		cur_frm.clear_table("invoices_reference");
		cur_frm.refresh_field('invoices_reference');
		frappe.call({
			doc : frm.doc,
			method : 'fetch_items',
			freeze : true,
			freeze_message : 'Getting All Items'
		}).then((res) => {
				refresh_field('invoices_reference');

				
		})
	}
});
