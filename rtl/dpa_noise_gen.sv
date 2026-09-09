// ========================================================================
// dpa_noise_gen.sv – генератор шума для маскировки энергопотребления
// Противодействие DPA (дифференциальный анализ мощности) путём
// добавления случайных токовых переходов и двухфазного такта.
// ========================================================================

module dpa_noise_gen (
    input  logic        clk,           // основной такт
    input  logic        rst_n,         // сброс
    input  logic        enable,        // включение защиты (после загрузки)
    input  logic        test_mode,     // отключаем для тестов
    output logic [31:0] noise_bus,     // шумовая шина для смешивания с данными
    output logic        wddl_clk,      // такт для двухрельсовой логики
    output logic        wddl_clk_n,    // инверсный такт
    output logic        power_random   // случайный бит для рандомизации питания
);

    // Два независимых LFSR с разными полиномами для генерации шума
    logic [31:0] lfsr_a, lfsr_b;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lfsr_a <= 32'h1234_5678;
            lfsr_b <= 32'h9ABC_DEF0;
        end else if (enable && !test_mode) begin
            // LFSR A: полином x^32 + x^22 + x^2 + x^1 + 1
            lfsr_a <= {lfsr_a[30:0], lfsr_a[31] ^ lfsr_a[21] ^ lfsr_a[1] ^ lfsr_a[0]};
            // LFSR B: полином x^32 + x^26 + x^23 + x^17 + 1
            lfsr_b <= {lfsr_b[30:0], lfsr_b[31] ^ lfsr_b[25] ^ lfsr_b[22] ^ lfsr_b[16]};
        end
    end

    // Объединение двух LFSR для создания широкополосного шума
    assign noise_bus = enable ? (lfsr_a ^ lfsr_b) : 32'h0;

    // Случайный бит для рандомизации токов (используется для маскировки)
    assign power_random = enable ? lfsr_a[31] ^ lfsr_b[30] : 1'b0;

    // Генерация двухфазного такта для WDDL (двухрельсовая логика)
    // Обе фазы равны по времени, но сдвинуты на 180°
    assign wddl_clk   = enable ? clk : 1'b0;
    assign wddl_clk_n = enable ? ~clk : 1'b1;

endmodule
