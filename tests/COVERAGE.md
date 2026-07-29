# Test coverage map

This file maps every numbered acceptance criterion from `spec.md` to
the test(s) that verify it. Each criterion has ≥1 test.

| #   | Criterion                                                | Test(s)                                                                                                                                            |
|-----|----------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| 1   | test_estimate_empty_text_returns_zero                    | test_estimator.py::test_estimate_empty_text_returns_zero_with_default_overhead, test_estimate_empty_text_with_zero_overhead_returns_zero             |
| 2   | test_estimate_ascii_is_deterministic                     | test_estimator.py::test_estimate_ascii_is_deterministic, test_estimate_ascii_lengths_match_4_bytes_per_token_rule, test_estimate_same_input_yields_identical_dict_keys |
| 3   | test_estimate_unicode_accounts_for_utf8                  | test_estimator.py::test_estimate_unicode_accounts_for_utf8, test_estimate_unicode_with_large_multibyte_share_triggers_surcharge, test_estimate_unicode_does_not_split_surrogate_pairs |
| 4   | test_estimate_emoji_is_deterministic                     | test_estimator.py::test_estimate_emoji_is_deterministic, test_estimate_mixed_emoji_and_ascii_does_not_count_emoji_as_ascii                            |
| 5   | test_estimate_returns_confidence_and_method              | test_estimator.py::test_estimate_returns_confidence_and_method, test_estimate_confidence_pure_ascii_is_high, test_estimate_confidence_pure_unicode_is_low, test_estimate_confidence_moderate_unicode_is_medium, test_estimate_confidence_control_byte_is_low, test_estimate_confidence_tab_newline_carriage_return_high |
| 6   | test_estimate_rejects_negative_overhead                  | test_estimator.py::test_estimate_rejects_negative_overhead, test_estimate_rejects_non_int_overhead, test_estimate_rejects_bool_overhead              |
| 7   | test_message_overhead_is_applied                         | test_estimator.py::test_message_overhead_is_applied, test_message_overhead_zero_is_distinct_from_default                                                |
| 8   | test_budget_report_sums_messages                         | test_budget.py::test_budget_report_sums_messages, test_budget_report_sums_messages_with_default_overhead, test_budget_report_empty_messages_yields_zero_total |
| 9   | test_budget_report_reports_remaining_capacity            | test_budget.py::test_budget_report_reports_remaining_capacity, test_budget_report_remaining_floored_at_zero                                          |
| 10  | test_budget_report_flags_overflow                        | test_budget.py::test_budget_report_flags_overflow, test_budget_report_overflow_exactly_at_limit_is_not_overflow                                      |
| 11  | test_budget_report_preserves_message_order               | test_budget.py::test_budget_report_preserves_message_order, test_budget_report_messages_tuple_is_immutable_view                                    |
| 12  | test_truncate_under_budget_returns_original              | test_truncation.py::test_truncate_under_budget_returns_original, test_truncate_exactly_at_budget_returns_original, test_truncate_empty_input_under_budget_returns_empty |
| 13  | test_truncate_tail_respects_budget                       | test_truncation.py::test_truncate_tail_respects_budget, test_truncate_tail_keeps_first_code_points, test_truncate_tail_zero_budget_returns_empty, test_truncate_tail_overhead_alone_fills_budget |
| 14  | test_truncate_head_respects_budget                       | test_truncation.py::test_truncate_head_respects_budget, test_truncate_head_keeps_last_code_points, test_truncate_head_zero_budget_returns_empty     |
| 15  | test_truncate_preserves_utf8_codepoints                  | test_truncation.py::test_truncate_preserves_utf8_codepoints, test_truncate_does_not_split_emoji_codepoints_tail, test_truncate_does_not_split_emoji_codepoints_head, test_truncate_does_not_split_cjk_codepoints |
| 16  | test_truncate_empty_input                                | test_truncation.py::test_truncate_empty_input_with_positive_budget, test_truncate_empty_input_with_zero_budget, test_truncate_empty_input_with_negative_budget_raises |
| 17  | test_truncate_rejects_negative_budget                    | test_truncation.py::test_truncate_rejects_negative_budget, test_truncate_rejects_non_int_budget, test_truncate_rejects_bool_budget                |
| 18  | test_truncate_reports_whether_content_was_cut            | test_truncation.py::test_truncate_reports_whether_content_was_cut, test_truncate_reports_original_token_count, test_truncate_result_dataclass_has_expected_fields |
| 19  | test_jsonl_estimate_request                              | test_jsonl_cli.py::test_jsonl_estimate_request_round_trip, test_jsonl_truncate_request_round_trip, test_jsonl_budget_request_round_trip, test_jsonl_estimate_request_with_unicode, test_jsonl_request_uses_compact_separators |
| 20  | test_jsonl_invalid_json_returns_structured_error         | test_jsonl_cli.py::test_jsonl_invalid_json_returns_structured_error, test_jsonl_invalid_json_keeps_dispatcher_alive, test_jsonl_blank_line_returns_empty_string |
| 21  | test_jsonl_unknown_operation_returns_error               | test_jsonl_cli.py::test_jsonl_unknown_operation_returns_error, test_jsonl_missing_op_returns_error, test_jsonl_non_string_op_returns_error, test_jsonl_non_object_request_returns_error, test_jsonl_null_request_returns_error |
| 22  | test_jsonl_response_is_single_line_json                  | test_jsonl_cli.py::test_jsonl_response_is_single_line_json, test_jsonl_response_handles_unicode_without_escaping                                    |
| 23  | test_mcp_tool_list_contains_three_tools                  | test_mcp_server.py::test_mcp_tool_list_contains_three_tools, test_mcp_tool_list_includes_descriptions_and_schemas, test_mcp_tools_constant_has_three_entries |
| 24  | test_mcp_estimate_tokens_tool_schema                     | test_mcp_server.py::test_mcp_estimate_tokens_tool_schema, test_mcp_estimate_tokens_tool_call_returns_structured_payload                              |
| 25  | test_mcp_truncate_text_tool_schema                       | test_mcp_server.py::test_mcp_truncate_text_tool_schema, test_mcp_truncate_text_tool_call_returns_truncated_payload                                  |
| 26  | test_mcp_context_budget_tool_schema                      | test_mcp_server.py::test_mcp_context_budget_tool_schema, test_mcp_context_budget_tool_call_returns_report_payload                                 |
| 27  | test_mcp_initialize_handshake                            | test_mcp_server.py::test_mcp_initialize_handshake, test_mcp_initialize_with_no_params, test_mcp_ping_returns_empty_object                          |
| 28  | test_mcp_unknown_method_returns_jsonrpc_error            | test_mcp_server.py::test_mcp_unknown_method_returns_jsonrpc_error, test_mcp_invalid_json_returns_parse_error, test_mcp_invalid_jsonrpc_returns_invalid_request, test_mcp_missing_method_returns_invalid_request, test_mcp_invalid_params_return_invalid_params, test_mcp_unknown_tool_returns_invalid_params, test_mcp_id_preserved_in_error_response |
| 29  | test_cli_reads_multiple_jsonl_requests                   | test_jsonl_cli.py::test_cli_reads_multiple_jsonl_requests, test_cli_processes_each_request_independently, test_cli_handles_large_request_stream, test_cli_empty_stdin_yields_zero_output |
| 30  | test_cli_does_not_write_logs_to_stdout                   | test_jsonl_cli.py::test_cli_does_not_write_logs_to_stdout, test_cli_diagnostic_output_goes_to_stderr, test_cli_quiet_flag_suppresses_stderr         |
| 31  | test_cli_nonzero_exit_on_malformed_request               | test_jsonl_cli.py::test_cli_nonzero_exit_on_malformed_request, test_cli_zero_exit_on_clean_run, test_cli_unknown_operation_yields_structured_error_with_nonzero_exit, test_cli_version_flag_prints_version, test_cli_help_flag_prints_help, test_cli_unknown_flag_exits_nonzero |
| 32  | test_long_input_completes_without_quadratic_behavior     | test_estimator.py::test_estimate_very_long_input_completes_quickly, test_truncation.py::test_truncate_long_input_completes_without_quadratic_behavior |
| 33  | test_null_character_is_counted                           | test_estimator.py::test_estimate_string_with_null_character_counted                                                                                |
| 34  | test_newline_and_tab_are_counted                         | test_estimator.py::test_estimate_newline_and_tab_counted_as_ascii                                                                                   |
| 35  | test_budget_report_accepts_role_content_messages         | test_budget.py::test_budget_report_accepts_role_content_messages, test_budget_report_accepts_name_field, test_budget_report_accepts_message_instances_directly |
| 36  | test_budget_report_rejects_missing_content               | test_budget.py::test_budget_report_rejects_missing_content, test_budget_report_rejects_missing_role, test_budget_report_rejects_non_string_content, test_budget_report_rejects_non_string_role, test_budget_report_rejects_non_string_name |
| 37  | test_public_functions_have_type_hints                    | test_contract.py::test_public_functions_have_type_hints[*], test_top_level_api_functions_have_hints                                                  |
| 38  | test_module_imports_without_third_party_packages          | test_contract.py::test_module_imports_without_third_party_packages, test_pyproject_declares_zero_runtime_dependencies, test_no_third_party_imports_inside_source |

**Summary**

- 38 / 38 spec acceptance criteria covered.
- 176 tests, all passing.
- Coverage source: `python3 -m pytest --collect-only -q | wc -l`.
