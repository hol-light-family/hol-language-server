(* Import path completion.
   Probes complete workspace entries: a folder, a file by prefix, by
   directory, and by longer prefix, the cursor past the closing quote,
   an import past the line start, and a second import on one line.
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

if true then needs "lib/util.ml" else needs "lib/util.ml";;
(* complete: then needs "lib/u => util.ml:file *)

needs "lib/util.ml";; needs "lib/util.ml";;
(* complete: needs "lib/util.ml";; needs "lib/u => util.ml:file *)
