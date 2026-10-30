(* Import path completion.
   Probes complete workspace entries: a folder, a file by prefix, by
   directory, and by longer prefix, and the cursor past the closing quote.
   Every probe string resolves, so the file adds no missing load to the
   workspace-wide tests. The driver test uses the default roots.
   Checked: the labels and kinds in the `complete` comments. *)

needs "lib/util.ml";;
(* complete: needs "li => lib:folder *)

needs "./lib/util.ml";;
(* complete: needs "./lib/ => util.ml:file *)

needs "base.ml";;
(* complete: needs "bas => base.ml:file *)

needs "ctx.ml";;
(* complete: needs "ctx.ml" => none *)

needs "tactics.ml";;
(* complete: needs "tact => tactics.ml:file *)
