        # =====================================================
        # FORMAT HELPER FOR STORE TABLES
        # =====================================================
        def _fmt_store(
            df_in: pd.DataFrame,
            include_impact: bool = True
        ) -> pd.DataFrame:

            cols = [
                "Label",
                "Điểm_mua_hàng",
                "Tổng_Gross",
                "Tổng_Net",
                "Số_đơn_hàng",
                "AOV",
                "Tỷ_lệ_CK (%)",
                "Change Gross%",
                "Change Net%",
                "Net Impact",
                "Change ĐH%",
            ]

            if not include_impact:
                cols = [
                    c for c in cols if c != "Net Impact"
                ]

            if "Region" in df_in.columns:
                cols.insert(2, "Region")

            cols = [
                c for c in cols if c in df_in.columns
            ]

            out = df_in[cols].rename(
                columns={"Label": "Kỳ"}
            ).copy()

            for c in [
                "Tổng_Gross",
                "Tổng_Net",
                "Số_đơn_hàng",
                "AOV",
            ]:
                if c in out.columns:
                    out[c] = out[c].apply(fmt_int)

            if "Tỷ_lệ_CK (%)" in out.columns:
                out["Tỷ_lệ_CK (%)"] = out[
                    "Tỷ_lệ_CK (%)"
                ].apply(lambda v: fmt_pct(v, 2))

            for c in [
                "Change Gross%",
                "Change Net%",
                "Change ĐH%",
            ]:
                if c in out.columns:
                    out[c] = out[c].apply(
                        lambda v: fmt_pct(
                            v, 2, with_sign=True
                        )
                    )

            if "Net Impact" in out.columns:
                out["Net Impact"] = out[
                    "Net Impact"
                ].apply(fmt_signed_int)

            return out

        # =====================================================
        # 1. BIẾN ĐỘNG THEO CỬA HÀNG
        # =====================================================
        with st.expander(
            f"📊 Biến động theo cửa hàng — {sel_period2}",
            expanded=False,
        ):
            metric_options = {
                "Net": "Change Net%",
                "Gross": "Change Gross%",
                "Đơn hàng": "Change ĐH%",
            }

            sel_metric_label = st.selectbox(
                "Chọn chỉ số biến động",
                list(metric_options.keys()),
                key=REV + "tb_change_metric",
            )

            sel_metric_col = metric_options[
                sel_metric_label
            ]

            chart_data = s_view.dropna(
                subset=[sel_metric_col]
            ).copy()

            if chart_data.empty:
                st.info(
                    "Không có dữ liệu biến động cho kỳ này "
                    "(kỳ đầu tiên không có kỳ trước để so sánh)."
                )

            else:
                chart_data = chart_data.sort_values(
                    sel_metric_col,
                    ascending=True,
                )

                fig_change = px.bar(
                    chart_data,
                    x=sel_metric_col,
                    y="Điểm_mua_hàng",
                    orientation="h",
                    text=chart_data[sel_metric_col].apply(
                        lambda v: fmt_pct(
                            v, 2, with_sign=True
                        )
                    ),
                )

                colors = np.where(
                    chart_data[sel_metric_col] >= 0,
                    "#2ECC71",
                    "#5B9BF0",
                )

                fig_change.update_traces(
                    marker_color=colors,
                    textposition="outside",
                    cliponaxis=False,
                )

                fig_change.update_layout(
                    xaxis_title=None,
                    yaxis_title=None,
                    yaxis=dict(
                        categoryorder="array",
                        categoryarray=chart_data[
                            "Điểm_mua_hàng"
                        ].tolist(),
                    ),
                    height=max(
                        300,
                        len(chart_data) * 35
                    ),
                    margin=dict(
                        l=0, r=40, t=10, b=0
                    ),
                )

                st.plotly_chart(
                    fig_change,
                    use_container_width=True,
                )

        # =====================================================
        # 2. TOP 10 THEO DOANH THU
        # =====================================================
        top10 = s_view.sort_values(
            "Tổng_Net",
            ascending=False
        ).head(10).copy()

        with st.expander(
            "🏆 TOP 10 ĐIỂM MUA HÀNG — THEO DOANH THU",
            expanded=False,
        ):
            st.dataframe(
                _fmt_store(top10),
                use_container_width=True,
                hide_index=True,
            )

        # =====================================================
        # 3. BOTTOM 10 THEO DOANH THU
        # =====================================================
        bottom10 = s_view.sort_values(
            "Tổng_Net",
            ascending=True
        ).head(10).copy()

        with st.expander(
            "📉 BOTTOM 10 ĐIỂM MUA HÀNG — THEO DOANH THU",
            expanded=False,
        ):
            st.dataframe(
                _fmt_store(bottom10),
                use_container_width=True,
                hide_index=True,
            )
