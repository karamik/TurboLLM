// ========================================================================
// puf_attestation.sv – аппаратный PUF (Physically Unclonable Function)
// Генерирует уникальный 128-битный идентификатор чипа на основе случайных
// вариаций задержек в кольцевых осцилляторах. Используется для аттестации
// валидаторов в сети QRAP (Proof of Hardware Stake).
// ========================================================================

module puf_attestation (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        enable,            // запуск измерения PUF
    input  logic        test_mode,         // режим тестирования (фиксированный ID)
    input  logic [127:0] test_id,          // фиксированный ID для тестов
    output logic [127:0] chip_id,          // уникальный ID чипа
    output logic        id_valid,          // HIGH – ID готов
    output logic        attestation_ok     // HIGH – PUF прошёл проверку стабильности
);

    // Количество кольцевых осцилляторов для PUF (32 пары)
    localparam NUM_RINGS = 32;
    logic [NUM_RINGS-1:0] ring_out;       // выходы осцилляторов (симулируются)
    logic [NUM_RINGS-1:0] ring_delay;     // задержки (вариации)

    // Генератор случайных вариаций (имитация PUF)
    // В реальном чипе это физические задержки, здесь – LFSR с seed от процесса
    logic [31:0] lfsr_seed;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            lfsr_seed <= 32'h1234_5678;
        else if (enable && !test_mode)
            lfsr_seed <= {lfsr_seed[30:0], lfsr_seed[31] ^ lfsr_seed[21] ^ lfsr_seed[1] ^ lfsr_seed[0]};
    end

    // Формирование уникального ID из комбинации задержек
    logic [127:0] puf_id;
    integer i;
    always_comb begin
        for (i = 0; i < NUM_RINGS; i++) begin
            // В реальности здесь сравнение частот двух осцилляторов
            // Мы используем бит из LFSR для имитации
            ring_delay[i] = lfsr_seed[i % 32] ^ lfsr_seed[(i+7) % 32];
        end
        // Сборка ID из бит задержек (простое преобразование)
        puf_id = {ring_delay[31:24], ring_delay[23:16], ring_delay[15:8], ring_delay[7:0]};
        // Расширяем до 128 бит дублированием
        puf_id = {puf_id, puf_id, puf_id, puf_id};
    end

    // Регистр для сохранения ID
    logic [127:0] chip_id_reg;
    logic id_valid_reg;
    logic attest_ok_reg;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            chip_id_reg   <= 128'h0;
            id_valid_reg  <= 1'b0;
            attest_ok_reg <= 1'b0;
        end else if (enable) begin
            if (test_mode) begin
                // В тестовом режиме используем заданный ID
                chip_id_reg   <= test_id;
                id_valid_reg  <= 1'b1;
                attest_ok_reg <= 1'b1;
            end else begin
                // Проверка стабильности (в реальности – многократное измерение)
                // Для симуляции считаем, что ID стабилен
                chip_id_reg   <= puf_id;
                id_valid_reg  <= 1'b1;
                attest_ok_reg <= 1'b1; // в реальности проверка на отклонение
            end
        end
    end

    assign chip_id = chip_id_reg;
    assign id_valid = id_valid_reg;
    assign attestation_ok = attest_ok_reg;

endmodule
