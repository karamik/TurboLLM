// ========================================================================
// active_shield.sv – защита от физического вмешательства (лазер, зондирование)
// Генерирует случайный меандр по верхнему слою металла над критическими блоками.
// При обрыве цепи – аварийное стирание (zeroization) и блокировка.
// ========================================================================

module active_shield (
    input  logic        clk,               // тактовый сигнал
    input  logic        rst_n,             // сброс (активный низкий)
    input  logic        shield_enable,     // включение защиты (после загрузки)
    input  logic        scan_mode,         // режим сканирования (отключает защиту для DFT)
    input  logic        test_mode,         // тестовый режим
    output logic        shield_ok,         // HIGH – меандр цел, защита активна
    output logic        shield_fault,      // HIGH – обнаружено нарушение целостности
    output logic        zeroize_req        // запрос на стирание ключей и сброс
);

    // Длина меандра (32 бита – можно менять под размеры кристалла)
    localparam SHIELD_PATTERN_LEN = 32;

    // Регистры для эталонного и фактического паттернов
    logic [SHIELD_PATTERN_LEN-1:0] expected_pattern;
    logic [SHIELD_PATTERN_LEN-1:0] actual_pattern;
    logic [SHIELD_PATTERN_LEN-1:0] pattern_reg;

    // Генератор псевдослучайной последовательности (LFSR) для меандра
    logic [31:0] lfsr;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lfsr <= 32'hDEAD_BEEF;   // начальное семя
        end else if (shield_enable && !scan_mode && !test_mode) begin
            // 32-битный LFSR с полиномом x^32 + x^22 + x^2 + x^1 + 1
            lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
        end
    end

    // Захват эталонного паттерна при первом включении (запоминается в защищённой памяти)
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            expected_pattern <= 32'h0;
        end else if (shield_enable && !scan_mode && !test_mode) begin
            if (expected_pattern == 32'h0)  // захват только один раз
                expected_pattern <= lfsr;
        end
    end

    // Фактический паттерн – считывается с физического меандра (в реальности через буфер)
    // Для симуляции используем тот же LFSR, но в реальном чипе это внешний сигнал.
    // Здесь мы эмулируем чтение через отдельный вход (можно будет подключить к пину).
    // Чтобы тестировать сбой, в тестбенче можно форсировать этот сигнал.
    assign actual_pattern = lfsr; // заглушка – заменить на реальный порт ввода

    // Сравнение с допустимым отклонением (учитываем флуктуации)
    logic mismatch;
    assign mismatch = (actual_pattern != expected_pattern) && shield_enable && !scan_mode && !test_mode;

    // Фильтр анти-дребезга (интегратор) – исключает кратковременные помехи
    logic [3:0] fault_counter;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fault_counter <= 4'h0;
            shield_fault  <= 1'b0;
            zeroize_req   <= 1'b0;
        end else if (scan_mode || test_mode) begin
            // В тестовых режимах защита отключается
            shield_fault  <= 1'b0;
            zeroize_req   <= 1'b0;
            fault_counter <= 4'h0;
        end else if (mismatch) begin
            if (fault_counter < 4'd15)
                fault_counter <= fault_counter + 1;
            else begin
                shield_fault <= 1'b1;
                zeroize_req  <= 1'b1;   // активация стирания
            end
        end else begin
            if (fault_counter > 0)
                fault_counter <= fault_counter - 1;
            else
                shield_fault <= 1'b0;
        end
    end

    // Сигнал целостности (OK)
    assign shield_ok = !shield_fault && shield_enable;

endmodule
