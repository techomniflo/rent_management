// Copyright (c) 2022, Gourav Saini and contributors
// For license information, please see license.txt

frappe.ui.form.on('Store Payment Calculator', {
	// refresh: function(frm) {

	// }
	calculate(frm){
		cur_frm.clear_table("items");
		cur_frm.refresh_field('items');
		frappe.call({
			doc:frm.doc,
			method:'fetch_items',
			freeze:'true',
			freeze_message:'Calculating'
		}).then((res) => {
			refresh_field('items');
		})		
	}
});
