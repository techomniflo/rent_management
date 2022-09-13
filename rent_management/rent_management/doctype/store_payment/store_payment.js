// Copyright (c) 2022, Gourav Saini and contributors
// For license information, please see license.txt

frappe.ui.form.on('Store Payment', {
	// refresh: function(frm) {

	// }
	get_outstanding(frm){
		cur_frm.clear_table("invoices_reference");
		cur_frm.clear_table("rent_reference");
		cur_frm.refresh_field('invoices_reference');
		cur_frm.refresh_field('rent_reference');
		frappe.call({
			doc : frm.doc,
			method : 'fetch_items',
			freeze : true,
			freeze_message : 'Getting All Items'
		}).then((res) => {
				refresh_field('invoices_reference');
				refresh_field('rent_reference');

				
		})
	},
	allocate: function(frm){
		frappe.call({
			doc : frm.doc,
			method : 'allocate_outstanding',
			freeze : true,
			freeze_message : 'Getting All Items'
		}).then((res) => {
				refresh_field('invoices_reference');
				refresh_field('rent_reference');	
		})
	},
	allocate_to_credit: function(frm){
		frappe.call({
			doc : frm.doc,
			method : 'allocate_credit',
			freeze : true,
			freeze_message : 'Getting All Items'
		}).then((res) => {
				refresh_field('invoices_reference');
				refresh_field('rent_reference');	
		})
	},

});
